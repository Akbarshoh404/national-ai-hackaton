"""Fast inputs: free text, voice, IMEI (and `POST /market/price-from-link` in the market router)."""

from __future__ import annotations

from fastapi import APIRouter, File, UploadFile

from app.deps import CompanyDep, DbDep
from app.errors import AppError
from app.schemas.inputs import ImeiIn, ImeiOut, ParsedItem, ParseIn, VoiceOut
from app.services import inputs, llm

router = APIRouter(prefix="/input", tags=["fast inputs (#19, #26)"])
MAX_AUDIO_BYTES = 10 * 1024 * 1024
AUDIO_TYPES = {"audio/ogg", "audio/mpeg", "audio/mp3", "audio/mp4", "audio/x-m4a", "audio/m4a", "audio/wav",
               "audio/x-wav", "audio/webm"}


@router.post("/parse", response_model=ParsedItem)
def input_parse(body: ParseIn, db: DbDep, _: CompanyDep) -> ParsedItem:
    """Free text ("cobalt 2021 45 ming probeg pozitsiya 4") → structured item + missing fields."""
    return ParsedItem(**inputs.parse_text(db, inputs.require_text(body.text), body.category_hint))


@router.post("/voice", response_model=VoiceOut)
async def input_voice(db: DbDep, _: CompanyDep, file: UploadFile = File(...)) -> VoiceOut:
    """Voice note (ogg/mp3/m4a/wav, ≤ 10 MB) → transcript → parsed item. 503 without an LLM key."""
    data = await file.read(MAX_AUDIO_BYTES + 1)
    if len(data) > MAX_AUDIO_BYTES:
        raise AppError("file_too_large", "Maximum audio size is 10 MB", 413)
    mime = (file.content_type or "audio/ogg").split(";")[0]
    if mime not in AUDIO_TYPES:
        raise AppError("unsupported_audio", "Send ogg, mp3, m4a or wav audio", 415, {"content_type": mime})
    if not llm.available():
        raise AppError("llm_unavailable", "Voice input needs GEMINI_API_KEY; please type instead", 503)
    transcript = llm.transcribe(data, mime)
    if not transcript:
        raise AppError("transcription_failed", "Could not transcribe the audio", 422)
    return VoiceOut(transcript=transcript, parsed=ParsedItem(**inputs.parse_text(db, transcript)))


@router.post("/imei", response_model=ImeiOut)
def input_imei(body: ImeiIn, _: CompanyDep) -> ImeiOut:
    """Luhn check + local demo TAC lookup (no external IMEI services)."""
    return ImeiOut(**inputs.check_imei(body.imei))
