FROM airbyte/source-declarative-manifest:0.57.0

# Copy all connector files
COPY . /airbyte/integration_code/

WORKDIR /airbyte/integration_code

# Install the package (includes custom components)
RUN pip install --no-cache-dir -e .

ENV AIRBYTE_ENTRYPOINT="python /airbyte/integration_code/main.py"
ENTRYPOINT ["python", "/airbyte/integration_code/main.py"]

LABEL io.airbyte.version=0.1.0
LABEL io.airbyte.name=airbyte/source-gong-transcripts