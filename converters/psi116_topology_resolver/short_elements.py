"""Explicitly selected short-element removal + port closure, on an isolated copy."""
from collections import Counter
from dataclasses import replace
from .connection_ports import PortModel, SUPPORTED
from .models import FixAction
from .resolver import resolve_psi116


def short_elements(doc, config):
    m=PortModel(doc,config);rows=[]
    source_nodes=[n for b in doc.branches for n in b.nodes]
    number_count=Counter(n.node_number for n in source_nodes if n.positive)
    refs=Counter((g[0].branch_index,g[0].component_ref_no) for g in m.groups)
    for gid,g in enumerate(m.groups):
        ports=m.group_ports.get(gid,[])
        if {p.node.endpoint for p in ports}!={1,2} or len(ports)!=2:continue
        span=max(a.position.distance_to(b.position) for a in g for b in g)
        if span>6+1e-9:continue
        first=next(p for p in ports if p.node.endpoint==1)
        last=next(p for p in ports if p.node.endpoint==2)
        order=m.branch_groups[g[0].branch_index];index=order.index(gid)
        left=m.group_ports.get(order[index-1],[]) if index else []
        right=m.group_ports.get(order[index+1],[]) if index+1<len(order) else []
        a=next((p for p in left if p.node.endpoint==2),left[-1] if left else None)
        b=next((p for p in right if p.node.endpoint==1),right[0] if right else None)
        reason=''
        if m.kind(gid) not in SUPPORTED or m.kind(gid) in {'BRAN','FBLI','CAP'}:reason='Boundary/unsupported component requires source review.'
        elif not g[0].component_ref_no or refs[(g[0].branch_index,g[0].component_ref_no)]!=1:reason='Component owner is not unique.'
        elif {n.key for n in source_nodes if n.branch_index==g[0].branch_index and n.component_ref_no==g[0].component_ref_no}!={n.key for n in g}:reason='Owner includes unmeasured or non-port source records.'
        elif any(not n.raw_component_type for n in g):reason='Explicit component type is required.'
        elif any(n.has_restraint or n.connection_type=='CLOS' for n in g):reason='Restraint or closed-end evidence must be retained.'
        elif any(n.positive and number_count[n.node_number]>sum(x.node_number==n.node_number for x in g) for n in g):reason='Node identity is shared outside the selected element.'
        elif not a or not b:reason='Both surrounding source ports are required.'
        elif a.node.position.distance_to(first.node.position)>config.connection_tolerance_mm or b.node.position.distance_to(last.node.position)>config.connection_tolerance_mm:reason='Element is not face-to-face with both surrounding ports.'
        elif not m.compatible(a,b,a.node.branch_index!=b.node.branch_index):reason='Surrounding diameter/direction/closure evidence does not qualify.'
        rows.append({'id':f'SHORT:{g[0].branch_index}:{g[0].component_ref_no}',
            'sourceSha256':doc.source_sha256,'branchIndex':g[0].branch_index,'branchName':g[0].branch_name,
            'componentType':m.kind(gid),'componentRefNo':g[0].component_ref_no,
            'lengthMm':span,'nodeKeys':[n.key for n in g],'recordCount':len(g),
            'weightRemoved':sum(n.weight or 0 for n in g),'eligible':not reason,'reason':reason,
            'leftKey':a.node.key if a else None,'rightKey':b.node.key if b else None})
    return rows


def apply_short_element(before, policy, config):
    from .transaction import (AppliedOperation,ValidationCheck,TopoFixTransactionResult,
        TransactionPolicy,apply_topofix_transaction,_parse_clone,_build_locator_index,
        _serialize,_record_sha,_child)
    policy.validate()
    if len(policy.short_element_requests)!=1 or policy.joint_repairs or policy.apply_all_safe:
        raise ValueError('Select one source-bound short element per atomic transaction.')
    request=policy.short_element_requests[0]
    if request.get('sourceSha256')!=before.document.source_sha256:raise ValueError('SHORT_ELEMENT_SOURCE_DRIFT')
    row=next((r for r in short_elements(before.document,config) if r['id']==request.get('id')),None)
    if not row or not row['eligible'] or list(request.get('nodeKeys',[]))!=row['nodeKeys']:
        raise ValueError('SHORT_ELEMENT_NOT_QUALIFIED_OR_WITNESS_DRIFT')
    if tuple(policy.selected_action_ids)!=(row['id'],):raise ValueError('SHORT_ELEMENT_SELECTION_DRIFT')
    if policy.require_no_blocking_plan_actions and any(a.status=='BLOCKED' or a.blockers for a in before.fix_actions):
        raise ValueError('BLOCKING_PLAN_ACTIONS_PRESENT')
    action=FixAction(action_id=row['id'],finding_ids=(),disposition='DROP_SELECTED_SHORT_ELEMENT',
        status='PROPOSED',confidence=1.,authority='OWNER_EXPLICIT_SHORT_ELEMENT_SELECTION',
        message=f"Drop selected {row['componentType']} ({row['lengthMm']:.3f} mm) and close its surrounding ports.",
        branch_name=row['branchName'],proposed_changes=(row,))
    original=[n for b in before.document.branches for n in b.nodes]
    by_key={n.key:n for n in original};removed=set(row['nodeKeys'])
    root=_parse_clone(before.document.source_text);loc=_build_locator_index(root,before)
    mapping={}
    for branch in before.document.branches:
        kept=[n for n in branch.nodes if n.key not in removed]
        for i,n in enumerate(kept):mapping[(branch.index,i)]=n
    left=by_key[row['leftKey']];right=by_key[row['rightKey']]
    for key in removed:loc[key].branch_element.remove(loc[key].node_element)
    candidate=_serialize(root,before.document.namespace)
    middle=resolve_psi116(candidate,config,source_name=before.document.source_path)
    reverse={n.key:pos for pos,n in mapping.items()}
    li,ri=reverse[left.key],reverse[right.key]
    l=middle.document.branches[li[0]].nodes[li[1]];r=middle.document.branches[ri[0]].nodes[ri[1]]
    stage=None
    if l.position.distance_to(r.position)>1e-7 or (l.positive and r.positive and l.node_number!=r.node_number):
        ports={l.key,r.key}
        closure=next((a for a in middle.fix_actions if a.disposition=='CLOSE_PORT_CONNECTION' and
            {a.proposed_changes[0]['movePortKey'],a.proposed_changes[0]['targetPortKey']}==ports),None)
        if closure is None:raise ValueError('SHORT_ELEMENT_RECONNECTION_NOT_QUALIFIED')
        stage=apply_topofix_transaction(middle,policy=TransactionPolicy(selected_action_ids=(closure.action_id,)),config=config)
        if not stage.committed:raise ValueError('SHORT_ELEMENT_RECONNECTION_REJECTED:'+','.join(stage.reject_reasons))
        candidate=stage.fixed_xml;after=stage.after_result
    else:after=middle
    operations=[]
    for n in original:
        if n.key in removed:
            operations.append(AppliedOperation(operation_id=f'OP-{len(operations)+1:06d}',action_id=action.action_id,
                disposition=action.disposition,operation='REMOVE_SELECTED_SHORT_ELEMENT_RECORD',branch_name=n.branch_name,
                source_node_key=n.key,source_node_number=n.node_number,before=n.raw_xml,after=None,
                authority=action.authority,source_xml_sha256=_record_sha(n)))
    for pos,n in mapping.items():
        actual=after.document.branches[pos[0]].nodes[pos[1]]
        source_el=loc[n.key].node_element
        import xml.etree.ElementTree as ET
        actual_el=ET.fromstring(actual.raw_xml)
        old={name:_child(source_el,name).text for name in ('NodeNumber','Position')}
        new={name:_child(actual_el,name).text for name in ('NodeNumber','Position')}
        if old==new:continue
        operations.append(AppliedOperation(operation_id=f'OP-{len(operations)+1:06d}',action_id=action.action_id,
            disposition=action.disposition,operation='CLOSE_COMPONENT_PORT',branch_name=n.branch_name,
            source_node_key=n.key,source_node_number=n.node_number,retained_node_key=left.key,
            retained_node_number=left.node_number,before=old,after=new,authority=action.authority,source_xml_sha256=_record_sha(n)))
    actual_nodes=[n for b in after.document.branches for n in b.nodes]
    expected=[n for n in original if n.key not in removed]
    identity=lambda n:(n.branch_index,n.component_ref_no,n.component_type,n.endpoint)
    closed_left=after.document.branches[li[0]].nodes[li[1]];closed_right=after.document.branches[ri[0]].nodes[ri[1]]
    checks=[
        ValidationCheck('SHORT_ELEMENT_LENGTH_LE_6',row['lengthMm']<=6+1e-9,True,'Selected physical component span is ≤6 mm.',row['lengthMm'],6),
        ValidationCheck('SELECTED_RECORD_REMOVAL_ACCOUNTED',len(original)-len(removed)==len(actual_nodes),True,'Only selected source records were removed.',len(original),len(actual_nodes),{'removed':len(removed)}),
        ValidationCheck('RETAINED_COMPONENT_OWNERS_PRESERVED',Counter(map(identity,expected))==Counter(map(identity,actual_nodes)),True,'All retained component/port identities are preserved.'),
        ValidationCheck('RESTRAINTS_PRESERVED',sum(n.has_restraint for n in original)==sum(n.has_restraint for n in actual_nodes),True,'No restraint was removed.'),
        ValidationCheck('WEIGHT_REMOVAL_ACCOUNTED',abs(sum(n.weight or 0 for n in expected)-sum(n.weight or 0 for n in actual_nodes))<1e-8,True,'Weight change equals only the explicitly selected component weight.',sum(n.weight or 0 for n in original),sum(n.weight or 0 for n in actual_nodes),{'selectedWeightRemoved':row['weightRemoved']}),
        ValidationCheck('CUT_PORTS_CLOSED',closed_left.position.distance_to(closed_right.position)<1e-7,True,'The surrounding ports coincide after removal and closure.'),
        ValidationCheck('NO_NEW_BLOCKING_FINDINGS',not({f.code for f in after.findings if f.blocking}-{f.code for f in before.findings if f.blocking}) and sum(f.blocking for f in after.findings)<=sum(f.blocking for f in before.findings),True,'No new blocking condition introduced by dropping the selected element.')]
    if stage:checks.extend(replace(c,code='CLOSURE_'+c.code,details={**c.details,'stage':'AFTER_SELECTED_REMOVAL'}) for c in stage.checks)
    reasons=tuple(c.code for c in checks if c.blocking and not c.passed)
    result=TopoFixTransactionResult(before,after,policy,(action,),tuple(operations),tuple(checks),reasons,
        None if reasons else candidate,config)
    if result.committed:
        from .lineage import build_topofix_source_lineage
        build_topofix_source_lineage(result)
    return result
