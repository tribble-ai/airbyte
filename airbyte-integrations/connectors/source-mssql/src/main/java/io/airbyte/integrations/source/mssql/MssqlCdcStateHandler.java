/*
 * Copyright (c) 2023 Airbyte, Inc., all rights reserved.
 */

package io.airbyte.integrations.source.mssql;

import static io.airbyte.integrations.source.mssql.MssqlSource.IS_COMPRESSED;
import static io.airbyte.integrations.source.mssql.MssqlSource.MSSQL_CDC_OFFSET;
import static io.airbyte.integrations.source.mssql.MssqlSource.MSSQL_DB_HISTORY;

import com.fasterxml.jackson.databind.JsonNode;
import io.airbyte.cdk.integrations.debezium.CdcStateHandler;
import io.airbyte.cdk.integrations.debezium.internals.AirbyteSchemaHistoryStorage.SchemaHistory;
import io.airbyte.cdk.integrations.source.relationaldb.models.CdcState;
import io.airbyte.cdk.integrations.source.relationaldb.state.StateManager;
import io.airbyte.commons.json.Jsons;
import io.airbyte.protocol.models.v0.AirbyteMessage;
import io.airbyte.protocol.models.v0.AirbyteMessage.Type;
import io.airbyte.protocol.models.v0.AirbyteStateMessage;
import java.util.HashMap;
import java.util.Map;
import java.util.Optional;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class MssqlCdcStateHandler implements CdcStateHandler {

  private static final Logger LOGGER = LoggerFactory.getLogger(MssqlCdcStateHandler.class);
  private final StateManager stateManager;

  public MssqlCdcStateHandler(final StateManager stateManager) {
    this.stateManager = stateManager;
  }

  @Override
  public boolean isCdcCheckpointEnabled() {
    return true;
  }

  @Override
  public AirbyteMessage saveState(final Map<String, String> offset, final SchemaHistory<String> dbHistory) {
    final Map<String, Object> state = new HashMap<>();
    state.put(MSSQL_CDC_OFFSET, offset);
    state.put(MSSQL_DB_HISTORY, dbHistory.schema());
    state.put(IS_COMPRESSED, dbHistory.isCompressed());

    final JsonNode asJson = Jsons.jsonNode(state);

    LOGGER.info("debezium state: {}", asJson);

    final CdcState cdcState = new CdcState().withState(asJson);
    stateManager.getCdcStateManager().setCdcState(cdcState);
    /*
     * Namespace pair is ignored by global state manager, but is needed for satisfy the API contract.
     * Therefore, provide an empty optional.
     */
    final AirbyteStateMessage stateMessage = stateManager.emit(Optional.empty());
    return new AirbyteMessage().withType(Type.STATE).withState(stateMessage);
  }

  @Override
  public AirbyteMessage saveStateAfterCompletionOfSnapshotOfNewStreams() {
    LOGGER.info("Snapshot of new tables is complete, saving state");
    /*
     * Namespace pair is ignored by global state manager, but is needed for satisfy the API contract.
     * Therefore, provide an empty optional.
     */
    final AirbyteStateMessage stateMessage = stateManager.emit(Optional.empty());
    return new AirbyteMessage().withType(Type.STATE).withState(stateMessage);
  }

  @Override
  public boolean compressSchemaHistoryForState() {
    return true;
  }

}
