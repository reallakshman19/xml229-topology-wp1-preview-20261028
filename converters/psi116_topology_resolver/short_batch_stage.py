"""A6b: explicit pre-Final batch Worker stage, separate from legacy singleton.

No global product admission: require topologyShortBatchExplicit true plus
2..32 source-bound eligible short owners. One atomic candidate per group,
one independent native/UXML canonical witness per hub group and independent
pre-Final replay. Original PSI116 is read only, never rewritten.
"""
from __future__ import annotations

from pathlib import Path
from time import perf_counter
import json

from .models import ResolverConfig
from .resolver import resolve_psi116
from .short_batch import (
    apply_independent_short_batch,verify_independent_short_batch_pre_final,
    ShortBatchRefused,MAX_INDEPENDENT_SHORT_BATCH,
)
from .short_batch_uxml import qualify_short_batch_uxml
from .short_memo import uxml_resolve
from .uxml_adapter import resolve_from_uxml
from .uxml_edit_ops import UxmlPatchError
from .transaction import TransactionPolicy
from .lineage import build_topofix_source_lineage
from .uxml_compare import _diff


def _emit(path,payload):
    Path(path).write_text(json.dumps(
        payload,sort_keys=True,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")


def run_explicit_batch_job(input_path:str,uxml:dict|None,
                           owner_ids:list[str],requests:list[dict],
                           paths:dict[str,str]):
    """Single immutable group job. Refusal means NO fixed XML is emitted."""
    started=perf_counter()
    config=ResolverConfig()
    baseline=resolve_psi116(Path(input_path),config)
    stage={"pyResolveMs":round((perf_counter()-started)*1000,3)}
    hub_parity={"status":"OFF","differences":[]}
    published=baseline
    if uxml is not None:
        t=perf_counter()
        try:
            adapted=uxml_resolve(uxml,config,
                                 source_name=str(input_path),
                                 resolver=resolve_from_uxml)
            differences=[]
            _diff("/findings",baseline.findings_payload(config),
                  adapted.findings_payload(config),differences)
            _diff("/fixPlan",baseline.fix_plan_payload(config),
                  adapted.fix_plan_payload(config),differences)
            hub_parity={"status":"DIFFERENT" if differences else "EQUAL",
                        "differences":differences}
            if not differences:
                published=adapted
        except (ValueError,TypeError,KeyError) as error:
            hub_parity={"status":"DIFFERENT",
                        "differences":["/uxmlReader:"+type(error).__name__+":"+
                                       str(error).split(":",1)[0]]}
        stage["pyHubParityMs"]=round((perf_counter()-t)*1000,3)
    _emit(paths["findings"],published.findings_payload(config))
    _emit(paths["plan"],published.fix_plan_payload(config))
    status={"requested":True,"generated":True,"committed":False,
            "rejectReasons":[],"fixedPath":"","lineagePath":"","handoffPath":"",
            "appliedEditOps":None,"opsPreview":None,
            "hubParity":hub_parity,"bulkTimings":stage}
    try:
        if uxml is not None and hub_parity["status"]!="EQUAL":
            raise ShortBatchRefused("UXML_SHORT_BATCH_INITIAL_PARITY_DIFFERENT")
        if not (2 <= len(owner_ids) <= MAX_INDEPENDENT_SHORT_BATCH and
                len(owner_ids)==len(set(owner_ids)) and
                len(owner_ids)==len(requests) and
                all(isinstance(item,str) and item.startswith("SHORT:")
                    for item in owner_ids)):
            raise ShortBatchRefused("SHORT_BATCH_EXPLICIT_GROUP_SIZE_REFUSED")
        policy=TransactionPolicy(
            selected_action_ids=tuple(owner_ids),
            short_element_requests=tuple(requests))
        t=perf_counter()
        if uxml is None:
            transaction=apply_independent_short_batch(
                baseline,policy=policy,config=config)
            status["bulkTimings"]["pyDirectMs"]=round(
                (perf_counter()-t)*1000,3)
        else:
            direct,patched,witness=qualify_short_batch_uxml(
                Path(input_path),uxml,policy=policy,config=config)
            status["bulkTimings"]["pyCanonicalGroupMs"]=round(
                (perf_counter()-t)*1000,3)
            if not witness["lossContractChecked"] or \
                    not witness["originalSourceCompared"] or \
                    witness["nativeVsUxmlParity"]!="EQUAL" or \
                    len(witness["ops"])!=len(owner_ids):
                raise ShortBatchRefused("SHORT_BATCH_CANONICAL_WITNESS_MISSING")
            transaction=patched
            status["appliedEditOps"]=witness["ops"]
        if not transaction.committed or transaction.fixed_xml is None:
            raise ShortBatchRefused("SHORT_BATCH_NOT_COMMITTED")
        t=perf_counter()
        prefinal=verify_independent_short_batch_pre_final(
            baseline.document.source_text,transaction,
            reviewed_action_ids=owner_ids)
        status["bulkTimings"]["pyPrefinalReplayMs"]=round(
            (perf_counter()-t)*1000,3)
        if not prefinal["requiresFreshWorkerBasis"] or \
           prefinal["nativeCiiReleaseAuthorized"] or \
           prefinal["ownerEvidenceCount"]!=len(owner_ids):
            raise ShortBatchRefused("SHORT_BATCH_PREFINAL_REPLAY_HOLD")
        lineage=build_topofix_source_lineage(transaction)
        if lineage!=prefinal["sourceLineage"]:
            raise ShortBatchRefused("SHORT_BATCH_LINEAGE_REPLAY_DRIFT")
        after=transaction.after_result
        if after is None:
            raise ShortBatchRefused("SHORT_BATCH_AFTER_RESOLUTION_MISSING")
        transaction_payload=transaction.transaction_payload()
        validation_payload=transaction.validation_payload()
        _emit(paths["transaction"],transaction_payload)
        _emit(paths["validation"],validation_payload)
        _emit(paths["lineage"],lineage)
        _emit(paths["handoff"],prefinal)
        _emit(paths["postFindings"],after.findings_payload(config))
        _emit(paths["postPlan"],after.fix_plan_payload(config))
        Path(paths["fixed"]).write_text(transaction.fixed_xml,
                                       encoding="utf-8")
        status["committed"]=True
        status["fixedPath"]=paths["fixed"]
        status["lineagePath"]=paths["lineage"]
        status["handoffPath"]=paths["handoff"]
        status["bulkTimings"]["pyTotalMs"]=round(
            (perf_counter()-started)*1000,3)
    except (ShortBatchRefused,UxmlPatchError,ValueError,KeyError,TypeError) as error:
        code=str(error).split(":",1)[0]
        status["rejectReasons"]=[code]
        status["committed"]=False
        status["appliedEditOps"]=None
        if uxml is not None:
            status["hubParity"]={"status":"DIFFERENT",
                                  "differences":["/batch:"+code]}
    _emit(paths["status"],status)
    return status
