# Gong Transcripts Source

A custom connector to fetch gong sentences, using airbyte. This is to be used to support a 1 time backfill operation of 
Uses a stream to get the call metadata since started_date, then pages through and gets all the sentences for those calls. 

## TODO

Careful, because it won't stop at 10000 api calls! Update the connector so it knows to do that. Then rebuild.

## Build

Build with
```docker build . -t airbyte/source-gong-transcripts:dev``` 

set a new tag with 

```docker tag airbyte/source-gong-transcripts:dev tribbleai/source-gong-transcripts:v[Whatever the tag Is e.g. 0.0.1]```

and then push it up

```docker push tribbleai/source-gong-transcripts:v0.1.0 ```

Then you can add it / upgrade it in airbyte.

## Adding it to airbyte

Now that it's tribble-ai dockerhub, just go to the customer's airbyte instance (http://localhost:8000/workspaces/their-workspace-id)

Go to settings --> sources

If it's not there, then add it with New Connector --> Add a new Docker Connector
- Image: 	`tribbleai/source-gong-transcripts`
- image tag: `whatever your version is`
- display name: `whatever you want`

If it's already there, then upgrade it by changing the version and clicking "Change". Add the stuff and run it. 

Once you have all the old transcripts, do some SQL magic to move them from ${schema}_integration/[airbyte tables] to ${schema}/gong_call_transcript_sentences



## Bot generated details about this connector

Take with grain of salt
- **Incremental Sync**: Efficiently syncs only new calls since the last sync (with 1-day lookback window)
- **Full Transcript Access**: Retrieves complete call transcripts with speaker identification
- **Sentence-Level Data**: Custom sentence extraction for granular analysis
- **User Management**: Syncs user profiles and settings

## Supported Streams

### 1. Call Metadata (`callMetadata`)
Primary incremental stream that fetches call metadata.

**Sync Mode**: Incremental (cursor on `started` field)

**Fields**:
- `id` (primary key)
- `calendarEventId`
- `direction`
- `duration`
- `isPrivate`
- `language`
- `media`
- `meetingUrl`
- `primaryUserId`
- `scheduled`
- `scope`
- `started` (incremental cursor)
- `system`
- `title`
- `url`
- `workspaceId`

### 2. Transcripts (`transcripts`)
Retrieves full transcripts for calls synced in the `callMetadata` stream.

**Sync Mode**: Full Refresh (sub-stream of `callMetadata`)

**Dependency**: Only fetches transcripts for calls returned by the `callMetadata` stream

**Structure**:
```json
{
  "callId": "string",
  "transcript": [
    {
      "speakerId": "string",
      "topic": "string",
      "sentences": [
        {
          "start": 0,
          "end": 3000,
          "text": "Hello world"
        }
      ]
    }
  ]
}
```

### 3. Sentences (`sentences`)
Flattened, sentence-level view of call transcripts using a custom extractor.

**Sync Mode**: Full Refresh (sub-stream of `callMetadata`)

**Dependency**: Only fetches sentences for calls returned by the `callMetadata` stream

**Primary Key**: Composite of `callId`, `monologue_index`, `sentence_index`

**Fields**:
- `callId`
- `speakerId`
- `topic`
- `monologue_index` (0-based index within the call)
- `sentence_index` (0-based index within the monologue)
- `start` (milliseconds)
- `end` (milliseconds)
- `duration_ms` (calculated duration)
- `text`

This stream uses a custom `SentenceExtractor` component to transform nested transcript structures into individual sentence records, making it easier to analyze conversations at a granular level.

### 4. Users (`users`)
Fetches user profiles and settings from your Gong workspace.

**Sync Mode**: Full Refresh

**Fields**:
- `id` (primary key)
- `active`
- `created`
- `emailAddress`
- `emailAliases`
- `firstName`
- `lastName`
- `personalMeetingUrls`
- `settings` (object with import/recording preferences)
- `spokenLanguages`
- `title`

## Configuration

### Required Fields

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `api_base_url` | string | Base URL for Gong API | `https://us-12345.api.gong.io` |
| `api_key` | string | Gong API access token | `your-api-key` |
| `start_date` | string | Initial sync start date (ISO-8601) | `2024-01-01T00:00:00Z` |

### Example Configuration

```json
{
  "api_base_url": "https://us-46083.api.gong.io",
  "api_key": "your-gong-api-key",
  "start_date": "2024-11-01T00:00:00Z"
}
```

## Authentication

This connector uses Bearer token authentication with the Gong API.

## Incremental Sync Behavior

The `callMetadata` stream implements incremental sync with the following characteristics:

- **Cursor Field**: `started` (call start time)
- **Lookback Window**: 1 day - re-syncs calls from the last day to catch late-arriving data
- **Initial Sync**: Uses `start_date` from configuration
- **Subsequent Syncs**: Uses last synced cursor value (minus 1 day)

The `transcripts` and `sentences` streams are sub-streams that depend on `callMetadata`:
- They only fetch data for **new calls** identified by the parent stream
- Setting `incremental_dependency: true` ensures they sync transcripts only for calls since the last sync
- This optimizes API usage and sync performance

## Rate Limiting

The connector implements exponential backoff for rate limiting:
- **Strategy**: Exponential backoff with factor of 2
- **Applies to**: All API requests
- The Gong API has rate limits that vary by plan; the connector automatically handles retries

### Custom Components

This connector includes a custom Python component:

**`SentenceExtractor`** (`source_gong_transcripts/components/sentence_extractor.py`)
- Implements `RecordExtractor` interface
- Flattens nested transcript structure into individual sentence records
- Adds computed fields: `monologue_index`, `sentence_index`, `duration_ms`

### Testing Locally

1. Set up a sample configuration in `sample_config.json`
2. Run connector check:
   ```bash
   python main.py check --config sample_config.json
   ```
3. Discover schema:
   ```bash
   python main.py discover --config sample_config.json
   ```
4. Read data:
   ```bash
   python main.py read --config sample_config.json --catalog configured_catalog.json
   ```

## Changelog

### Version 0.57.0
- Initial implementation with declarative YAML manifest
- Incremental sync on call metadata with 1-day lookback
- Custom sentence extractor for granular transcript analysis
- Support for transcripts, sentences, and users streams
- Bearer token authentication
- Exponential backoff for rate limiting

## Support

For issues, questions, or feature requests, please refer to the Gong API documentation:
- [Gong API Documentation](https://gong.app.gong.io/settings/api/documentation)
- [Authentication Guide](https://help.gong.io/hc/en-us/articles/360042993991-API-Authentication)

## License

MIT License