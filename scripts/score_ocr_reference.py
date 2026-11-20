"""Score Tesseract Chinese OCR against manually transcribed keyframe labels."""
from __future__ import annotations
import argparse, json, re
from pathlib import Path

def normalize(value: str) -> str:
    return "".join(re.findall(r"[\u3400-\u4dbf\u4e00-\u9fff]", value))

def edit_distance(reference: str, hypothesis: str) -> int:
    previous=list(range(len(hypothesis)+1))
    for i, ref_char in enumerate(reference, start=1):
        current=[i]
        for j, hyp_char in enumerate(hypothesis, start=1):
            current.append(min(current[-1]+1, previous[j]+1, previous[j-1]+(ref_char != hyp_char)))
        previous=current
    return previous[-1]

def main() -> None:
    p=argparse.ArgumentParser()
    p.add_argument("--ocr-report",required=True,type=Path)
    p.add_argument("--ground-truth",required=True,type=Path)
    p.add_argument("--output",required=True,type=Path)
    a=p.parse_args()
    report=json.loads(a.ocr_report.read_text(encoding="utf-8"))
    truth=json.loads(a.ground_truth.read_text(encoding="utf-8"))
    predictions={x["frame"]:x.get("text","") for x in report["frames"]}
    rows=[]; edits=chars=0; missing=[]
    for item in truth["frames"]:
        frame=item["frame"]; ref=normalize(item["reference"])
        hyp=normalize(predictions[frame]) if frame in predictions else ""
        if frame not in predictions: missing.append(frame)
        distance=edit_distance(ref,hyp); edits+=distance; chars+=len(ref)
        rows.append({"frame":frame,"timestamp_seconds":item["timestamp_seconds"],"reference":ref,"hypothesis":hyp,"edit_distance":distance,"reference_characters":len(ref),"cer":round(distance/len(ref),6) if ref else None})
    cer=edits/chars if chars else 1.0
    result={"status":"SCORED" if not missing else "INCOMPLETE","metric":"Chinese-character CER (edit distance / reference characters)","dataset":truth["dataset"],"frames_scored":len(rows)-len(missing),"frames_expected":len(rows),"missing_frames":missing,"total_edit_distance":edits,"total_reference_characters":chars,"cer":round(cer,6),"character_accuracy_proxy":round(max(0.0,1.0-cer),6),"interpretation":"Diagnostic score on 10 manually labeled keyframes only; not a general OCR accuracy estimate.","frames":rows}
    a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({k:v for k,v in result.items() if k!="frames"},ensure_ascii=False,indent=2))
    if missing: raise SystemExit(2)
if __name__=="__main__": main()
