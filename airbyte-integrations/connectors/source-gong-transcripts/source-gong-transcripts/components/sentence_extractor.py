"""
Custom record extractor for flattening Gong transcript sentences
"""
from typing import Any, Iterable, Mapping
from airbyte_cdk.sources.declarative.extractors.record_extractor import RecordExtractor


class SentenceExtractor(RecordExtractor):
    """
    Extracts individual sentences from Gong transcript structure.
    
    Transforms:
    {
        "callId": "123",
        "transcript": [
            {
                "speakerId": "speaker1",
                "topic": "Introduction",
                "sentences": [
                    {"start": 0, "end": 3000, "text": "Hello"},
                    {"start": 3000, "end": 6000, "text": "How are you"}
                ]
            }
        ]
    }
    
    Into multiple records:
    [
        {
            "callId": "123",
            "speakerId": "speaker1",
            "topic": "Introduction",
            "monologue_index": 0,
            "sentence_index": 0,
            "start": 0,
            "end": 3000,
            "duration_ms": 3000,
            "text": "Hello"
        },
        {
            "callId": "123",
            "speakerId": "speaker1",
            "topic": "Introduction",
            "monologue_index": 0,
            "sentence_index": 1,
            "start": 3000,
            "end": 6000,
            "duration_ms": 3000,
            "text": "How are you"
        }
    ]
    """
    
    def extract_records(self, response: Mapping[str, Any]) -> Iterable[Mapping[str, Any]]:
        """
        Extract flattened sentence records from Gong API response
        
        Args:
            response: The API response containing callTranscripts
            
        Yields:
            Individual sentence records with call and monologue context
        """
        call_transcripts = response.get("callTranscripts", [])
        
        for call in call_transcripts:
            call_id = call.get("callId")
            transcript = call.get("transcript", [])
            
            for monologue_idx, monologue in enumerate(transcript):
                speaker_id = monologue.get("speakerId")
                topic = monologue.get("topic")
                sentences = monologue.get("sentences", [])
                
                for sentence_idx, sentence in enumerate(sentences):
                    start = sentence.get("start")
                    end = sentence.get("end")
                    
                    # Calculate duration
                    duration_ms = None
                    if start is not None and end is not None:
                        duration_ms = end - start
                    
                    yield {
                        "callId": call_id,
                        "speakerId": speaker_id,
                        "topic": topic,
                        "monologue_index": monologue_idx,
                        "sentence_index": sentence_idx,
                        "start": start,
                        "end": end,
                        "duration_ms": duration_ms,
                        "text": sentence.get("text")
                    }