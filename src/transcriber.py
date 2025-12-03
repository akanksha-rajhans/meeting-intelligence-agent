import assemblyai as aai
from src.config import ASSEMBLYAI_API_KEY, PROCESSED_DIR
from pathlib import Path

aai.settings.api_key = ASSEMBLYAI_API_KEY

def transcribe_audio(audio_path: Path) -> str:
    print(f"🎙️  Transcribing {audio_path.name}")
    transcriber = aai.Transcriber()
    transcript  = transcriber.transcribe(str(audio_path))
    if transcript.status == aai.TranscriptStatus.error:
        raise RuntimeError(transcript.error)
    # save
    out = PROCESSED_DIR / f"{audio_path.stem}_transcript.txt"
    out.write_text(transcript.text)
    print(f"✅ Transcript saved: {out.name}")
    return transcript.text