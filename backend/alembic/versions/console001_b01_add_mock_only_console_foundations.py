"""add mock-only Console foundations"""
from alembic import op
import sqlalchemy as sa
from app.core.database import UTCDateTime

revision = 'console001_b01'
down_revision = 'c2026101601'
branch_labels = None
depends_on = None


def upgrade():

    op.create_table('console_clients',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('security_id', sa.String(length=32), nullable=False),
    sa.Column('lab_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('normalized_name', sa.String(length=240), nullable=False),
    sa.Column('ipv4', sa.String(length=15), nullable=False),
    sa.Column('ssh_port', sa.Integer(), nullable=False),
    sa.Column('ssh_username', sa.String(length=256), nullable=False),
    sa.Column('auth_method', sa.String(length=16), nullable=False),
    sa.Column('active_credential_id', sa.Integer(), nullable=True),
    sa.Column('enabled', sa.Boolean(), nullable=False),
    sa.Column('notes', sa.Text(), nullable=False),
    sa.Column('metadata_version', sa.Integer(), nullable=False),
    sa.Column('connection_epoch', sa.Integer(), nullable=False),
    sa.Column('updated_at', UTCDateTime(), nullable=False),
    sa.Column('updated_by', sa.Integer(), nullable=False),
    sa.Column('created_at', UTCDateTime(), nullable=False),
    sa.CheckConstraint("auth_method IN ('password','private_key')", name=op.f('ck_console_clients_method')),
    sa.CheckConstraint('length(trim(name)) > 0', name=op.f('ck_console_clients_name')),
    sa.CheckConstraint('metadata_version > 0 AND connection_epoch > 0', name=op.f('ck_console_clients_versions')),
    sa.CheckConstraint('ssh_port BETWEEN 1 AND 65535', name=op.f('ck_console_clients_port')),
    sa.ForeignKeyConstraint(['active_credential_id'], ['console_credentials.id'], name=op.f('fk_console_clients_active_credential_id_console_credentials'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['lab_id'], ['labs.id'], name=op.f('fk_console_clients_lab_id_labs'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['updated_by'], ['users.id'], name=op.f('fk_console_clients_updated_by_users'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_console_clients')),
    sa.UniqueConstraint('ipv4', name=op.f('uq_console_clients_ipv4')),
    sa.UniqueConstraint('lab_id', 'normalized_name', name=op.f('uq_console_clients_lab_id')),
    sa.UniqueConstraint('security_id', name=op.f('uq_console_clients_security_id'))
    )
    op.create_table('console_credentials',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('security_id', sa.String(length=32), nullable=False),
    sa.Column('client_security_id', sa.String(length=32), nullable=False),
    sa.Column('method', sa.String(length=16), nullable=False),
    sa.Column('ciphertext', sa.LargeBinary(), nullable=False),
    sa.Column('nonce', sa.LargeBinary(), nullable=False),
    sa.Column('wrapped_data_key', sa.LargeBinary(), nullable=False),
    sa.Column('wrap_nonce', sa.LargeBinary(), nullable=False),
    sa.Column('key_id', sa.String(length=64), nullable=False),
    sa.Column('algorithm', sa.String(length=32), nullable=False),
    sa.Column('generation', sa.Integer(), nullable=False),
    sa.Column('crypto_revision', sa.Integer(), nullable=False),
    sa.Column('replaced_at', UTCDateTime(), nullable=True),
    sa.Column('created_by', sa.Integer(), nullable=False),
    sa.Column('created_at', UTCDateTime(), nullable=False),
    sa.CheckConstraint("method IN ('password','private_key')", name=op.f('ck_console_credentials_method')),
    sa.CheckConstraint('generation > 0 AND crypto_revision > 0', name=op.f('ck_console_credentials_versions')),
    sa.ForeignKeyConstraint(['client_security_id'], ['console_clients.security_id'], name=op.f('fk_console_credentials_client_security_id_console_clients'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_console_credentials_created_by_users'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_console_credentials')),
    sa.UniqueConstraint('client_security_id', 'generation', name=op.f('uq_console_credentials_client_security_id')),
    sa.UniqueConstraint('security_id', name=op.f('uq_console_credentials_security_id'))
    )
    op.create_table('console_confirmations',
    sa.Column('token_digest', sa.String(length=64), nullable=False),
    sa.Column('actor_id', sa.Integer(), nullable=False),
    sa.Column('login_session_digest', sa.String(length=64), nullable=False),
    sa.Column('subject', sa.String(length=64), nullable=False),
    sa.Column('payload_hash', sa.String(length=64), nullable=False),
    sa.Column('sessions_hash', sa.String(length=64), nullable=False),
    sa.Column('expires_at', UTCDateTime(), nullable=False),
    sa.Column('used_at', UTCDateTime(), nullable=True),
    sa.Column('created_at', UTCDateTime(), nullable=False),
    sa.ForeignKeyConstraint(['actor_id'], ['users.id'], name=op.f('fk_console_confirmations_actor_id_users'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('token_digest', name=op.f('pk_console_confirmations'))
    )
    op.create_table('console_audits',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('actor_id', sa.Integer(), nullable=True),
    sa.Column('sut_id', sa.Integer(), nullable=True),
    sa.Column('event_type', sa.String(length=64), nullable=False),
    sa.Column('details', sa.JSON(), nullable=False),
    sa.Column('created_at', UTCDateTime(), nullable=False),
    sa.ForeignKeyConstraint(['actor_id'], ['users.id'], name=op.f('fk_console_audits_actor_id_users'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['sut_id'], ['suts.id'], name=op.f('fk_console_audits_sut_id_suts'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_console_audits'))
    )
    op.create_table('console_bmc_endpoints',
    sa.Column('sut_id', sa.Integer(), nullable=False),
    sa.Column('ipv4', sa.String(length=15), nullable=True),
    sa.Column('revision', sa.Integer(), nullable=False),
    sa.Column('endpoint_epoch', sa.Integer(), nullable=False),
    sa.Column('updated_at', UTCDateTime(), nullable=False),
    sa.Column('updated_by', sa.Integer(), nullable=False),
    sa.CheckConstraint('revision > 0 AND endpoint_epoch > 0', name=op.f('ck_console_bmc_endpoints_versions')),
    sa.ForeignKeyConstraint(['sut_id'], ['suts.id'], name=op.f('fk_console_bmc_endpoints_sut_id_suts'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['updated_by'], ['users.id'], name=op.f('fk_console_bmc_endpoints_updated_by_users'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('sut_id', name=op.f('pk_console_bmc_endpoints'))
    )
    op.create_table('console_grants',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('sut_id', sa.Integer(), nullable=False),
    sa.Column('admin_id', sa.Integer(), nullable=False),
    sa.Column('expires_at', UTCDateTime(), nullable=False),
    sa.Column('reason', sa.String(length=1000), nullable=True),
    sa.Column('state', sa.String(length=8), nullable=False),
    sa.Column('revision', sa.Integer(), nullable=False),
    sa.Column('closed_at', UTCDateTime(), nullable=True),
    sa.Column('close_reason', sa.String(length=40), nullable=True),
    sa.Column('created_at', UTCDateTime(), nullable=False),
    sa.CheckConstraint("state IN ('active','expired','revoked')", name=op.f('ck_console_grants_state')),
    sa.CheckConstraint('expires_at > created_at AND julianday(expires_at) <= julianday(created_at) + 1', name=op.f('ck_console_grants_duration')),
    sa.ForeignKeyConstraint(['admin_id'], ['users.id'], name=op.f('fk_console_grants_admin_id_users'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['sut_id'], ['suts.id'], name=op.f('fk_console_grants_sut_id_suts'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_console_grants_user_id_users'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_console_grants'))
    )
    with op.batch_alter_table('console_grants', schema=None) as batch_op:
        batch_op.create_index('uq_console_grant_active', ['user_id', 'sut_id'], unique=True, sqlite_where=sa.text("state = 'active'"))

    op.create_table('console_mapping_events',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('sut_id', sa.Integer(), nullable=False),
    sa.Column('transport', sa.String(length=4), nullable=False),
    sa.Column('actor_id', sa.Integer(), nullable=False),
    sa.Column('old', sa.JSON(), nullable=False),
    sa.Column('new', sa.JSON(), nullable=False),
    sa.Column('reason', sa.String(length=1000), nullable=True),
    sa.Column('created_at', UTCDateTime(), nullable=False),
    sa.ForeignKeyConstraint(['actor_id'], ['users.id'], name=op.f('fk_console_mapping_events_actor_id_users'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['sut_id'], ['suts.id'], name=op.f('fk_console_mapping_events_sut_id_suts'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_console_mapping_events'))
    )
    with op.batch_alter_table('console_mapping_events', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_console_mapping_events_sut_id'), ['sut_id'], unique=False)

    op.create_table('console_uart_mappings',
    sa.Column('sut_id', sa.Integer(), nullable=False),
    sa.Column('client_id', sa.Integer(), nullable=True),
    sa.Column('tmux_session', sa.String(length=64), nullable=True),
    sa.Column('revision', sa.Integer(), nullable=False),
    sa.Column('endpoint_epoch', sa.Integer(), nullable=False),
    sa.Column('active_slot', sa.Boolean(), nullable=False),
    sa.Column('updated_at', UTCDateTime(), nullable=False),
    sa.Column('updated_by', sa.Integer(), nullable=False),
    sa.CheckConstraint('(client_id IS NULL AND tmux_session IS NULL) OR (client_id IS NOT NULL AND tmux_session IS NOT NULL)', name=op.f('ck_console_uart_mappings_configured_pair')),
    sa.CheckConstraint('revision > 0 AND endpoint_epoch > 0', name=op.f('ck_console_uart_mappings_versions')),
    sa.ForeignKeyConstraint(['client_id'], ['console_clients.id'], name=op.f('fk_console_uart_mappings_client_id_console_clients'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['sut_id'], ['suts.id'], name=op.f('fk_console_uart_mappings_sut_id_suts'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['updated_by'], ['users.id'], name=op.f('fk_console_uart_mappings_updated_by_users'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('sut_id', name=op.f('pk_console_uart_mappings'))
    )
    with op.batch_alter_table('console_uart_mappings', schema=None) as batch_op:
        batch_op.create_index('uq_console_uart_active_pair', ['client_id', 'tmux_session'], unique=True, sqlite_where=sa.text('active_slot = 1'))

    op.create_table('console_host_keys',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('client_id', sa.Integer(), nullable=True),
    sa.Column('bmc_sut_id', sa.Integer(), nullable=True),
    sa.Column('ipv4', sa.String(length=15), nullable=False),
    sa.Column('port', sa.Integer(), nullable=False),
    sa.Column('endpoint_epoch', sa.Integer(), nullable=False),
    sa.Column('algorithm', sa.String(length=64), nullable=False),
    sa.Column('public_key', sa.Text(), nullable=False),
    sa.Column('fingerprint', sa.String(length=100), nullable=False),
    sa.Column('trust_revision', sa.Integer(), nullable=False),
    sa.Column('is_current', sa.Boolean(), nullable=False),
    sa.Column('previous_id', sa.Integer(), nullable=True),
    sa.Column('accepted_by', sa.Integer(), nullable=False),
    sa.Column('replaced_at', UTCDateTime(), nullable=True),
    sa.Column('created_at', UTCDateTime(), nullable=False),
    sa.CheckConstraint('(client_id IS NOT NULL AND bmc_sut_id IS NULL) OR (client_id IS NULL AND bmc_sut_id IS NOT NULL)', name=op.f('ck_console_host_keys_owner')),
    sa.ForeignKeyConstraint(['accepted_by'], ['users.id'], name=op.f('fk_console_host_keys_accepted_by_users'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['bmc_sut_id'], ['console_bmc_endpoints.sut_id'], name=op.f('fk_console_host_keys_bmc_sut_id_console_bmc_endpoints'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['client_id'], ['console_clients.id'], name=op.f('fk_console_host_keys_client_id_console_clients'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['previous_id'], ['console_host_keys.id'], name=op.f('fk_console_host_keys_previous_id_console_host_keys'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_console_host_keys'))
    )
    with op.batch_alter_table('console_host_keys', schema=None) as batch_op:
        batch_op.create_index('uq_console_host_key_bmc', ['bmc_sut_id'], unique=True, sqlite_where=sa.text('is_current = 1'))
        batch_op.create_index('uq_console_host_key_client', ['client_id'], unique=True, sqlite_where=sa.text('is_current = 1'))

    op.create_table('console_sessions',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('sut_id', sa.Integer(), nullable=False),
    sa.Column('client_id', sa.Integer(), nullable=True),
    sa.Column('login_session_digest', sa.String(length=64), nullable=False),
    sa.Column('transport', sa.String(length=4), nullable=False),
    sa.Column('mode', sa.String(length=5), nullable=False),
    sa.Column('policy', sa.String(length=20), nullable=False),
    sa.Column('grant_id', sa.Integer(), nullable=True),
    sa.Column('usage_key', sa.String(length=64), nullable=True),
    sa.Column('slot', sa.Integer(), nullable=True),
    sa.Column('state', sa.String(length=12), nullable=False),
    sa.Column('instance_id', sa.String(length=64), nullable=False),
    sa.Column('attachment_generation', sa.Integer(), nullable=False),
    sa.Column('endpoint_epoch', sa.Integer(), nullable=False),
    sa.Column('client_epoch', sa.Integer(), nullable=False),
    sa.Column('credential_generation', sa.Integer(), nullable=False),
    sa.Column('trust_revision', sa.Integer(), nullable=False),
    sa.Column('lease_until', UTCDateTime(), nullable=False),
    sa.Column('connected_at', UTCDateTime(), nullable=True),
    sa.Column('closed_at', UTCDateTime(), nullable=True),
    sa.Column('close_reason', sa.String(length=40), nullable=True),
    sa.Column('created_at', UTCDateTime(), nullable=False),
    sa.CheckConstraint("(state = 'closed' AND slot IS NULL) OR (state != 'closed' AND slot BETWEEN 1 AND 10 AND slot IS NOT NULL)", name=op.f('ck_console_sessions_slot')),
    sa.CheckConstraint("mode IN ('read','write')", name=op.f('ck_console_sessions_mode')),
    sa.CheckConstraint("state IN ('reserved','connecting','connected','reconnecting','closed')", name=op.f('ck_console_sessions_state')),
    sa.CheckConstraint("transport IN ('uart','bmc')", name=op.f('ck_console_sessions_transport')),
    sa.ForeignKeyConstraint(['client_id'], ['console_clients.id'], name=op.f('fk_console_sessions_client_id_console_clients'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['grant_id'], ['console_grants.id'], name=op.f('fk_console_sessions_grant_id_console_grants'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['sut_id'], ['suts.id'], name=op.f('fk_console_sessions_sut_id_suts'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_console_sessions_user_id_users'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_console_sessions')),
    sa.UniqueConstraint('user_id', 'slot', name=op.f('uq_console_sessions_user_id'))
    )
    with op.batch_alter_table('console_sessions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_console_sessions_lease_until'), ['lease_until'], unique=False)
        batch_op.create_index(batch_op.f('ix_console_sessions_login_session_digest'), ['login_session_digest'], unique=False)

    op.create_table('console_auth_flows',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('session_id', sa.String(length=32), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('login_session_digest', sa.String(length=64), nullable=False),
    sa.Column('attachment_generation', sa.Integer(), nullable=False),
    sa.Column('attempt_count', sa.Integer(), nullable=False),
    sa.Column('in_flight', sa.Boolean(), nullable=False),
    sa.Column('expires_at', UTCDateTime(), nullable=False),
    sa.Column('closed_at', UTCDateTime(), nullable=True),
    sa.Column('created_at', UTCDateTime(), nullable=False),
    sa.CheckConstraint('attempt_count BETWEEN 0 AND 3', name=op.f('ck_console_auth_flows_attempts')),
    sa.ForeignKeyConstraint(['session_id'], ['console_sessions.id'], name=op.f('fk_console_auth_flows_session_id_console_sessions'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_console_auth_flows_user_id_users'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_console_auth_flows'))
    )
    op.create_table('console_revocations',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('session_id', sa.String(length=32), nullable=False),
    sa.Column('attachment_generation', sa.Integer(), nullable=False),
    sa.Column('target_epoch', sa.Integer(), nullable=False),
    sa.Column('reason', sa.String(length=40), nullable=False),
    sa.Column('delivered_at', UTCDateTime(), nullable=True),
    sa.Column('created_at', UTCDateTime(), nullable=False),
    sa.ForeignKeyConstraint(['session_id'], ['console_sessions.id'], name=op.f('fk_console_revocations_session_id_console_sessions'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_console_revocations')),
    sa.UniqueConstraint('session_id', 'attachment_generation', name=op.f('uq_console_revocations_session_id'))
    )
    op.create_table('console_tickets',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('token_digest', sa.String(length=64), nullable=False),
    sa.Column('session_id', sa.String(length=32), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('login_session_digest', sa.String(length=64), nullable=False),
    sa.Column('origin', sa.String(length=256), nullable=False),
    sa.Column('attachment_generation', sa.Integer(), nullable=False),
    sa.Column('endpoint_epoch', sa.Integer(), nullable=False),
    sa.Column('expires_at', UTCDateTime(), nullable=False),
    sa.Column('used_at', UTCDateTime(), nullable=True),
    sa.Column('created_at', UTCDateTime(), nullable=False),
    sa.ForeignKeyConstraint(['session_id'], ['console_sessions.id'], name=op.f('fk_console_tickets_session_id_console_sessions'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_console_tickets_user_id_users'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_console_tickets')),
    sa.UniqueConstraint('token_digest', name=op.f('uq_console_tickets_token_digest'))
    )
    install_guards()


def downgrade():
    connection = op.get_bind()
    tables = [name for name in sa.inspect(connection).get_table_names() if name.startswith("console_")]
    if any(connection.execute(sa.text('SELECT count(*) FROM "' + name + '"')).scalar() for name in tables):
        raise RuntimeError("Console data exists; restore a compatible pre-upgrade backup instead of destructive downgrade")
    for name in GUARDS:
        op.execute('DROP TRIGGER IF EXISTS "' + name + '"')

    op.drop_table('console_tickets')
    op.drop_table('console_revocations')
    op.drop_table('console_auth_flows')
    with op.batch_alter_table('console_sessions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_console_sessions_login_session_digest'))
        batch_op.drop_index(batch_op.f('ix_console_sessions_lease_until'))

    op.drop_table('console_sessions')
    with op.batch_alter_table('console_host_keys', schema=None) as batch_op:
        batch_op.drop_index('uq_console_host_key_client', sqlite_where=sa.text('is_current = 1'))
        batch_op.drop_index('uq_console_host_key_bmc', sqlite_where=sa.text('is_current = 1'))

    op.drop_table('console_host_keys')
    with op.batch_alter_table('console_uart_mappings', schema=None) as batch_op:
        batch_op.drop_index('uq_console_uart_active_pair', sqlite_where=sa.text('active_slot = 1'))

    op.drop_table('console_uart_mappings')
    with op.batch_alter_table('console_mapping_events', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_console_mapping_events_sut_id'))

    op.drop_table('console_mapping_events')
    with op.batch_alter_table('console_grants', schema=None) as batch_op:
        batch_op.drop_index('uq_console_grant_active', sqlite_where=sa.text("state = 'active'"))

    op.drop_table('console_grants')
    op.drop_table('console_bmc_endpoints')
    op.drop_table('console_audits')
    op.drop_table('console_confirmations')
    op.drop_table('console_credentials')
    op.drop_table('console_clients')



# Frozen revision-local SQL: no runtime model dependency or existing-table rewrite.
GUARDS = {}


def guard(name, sql):
    GUARDS[name] = "CREATE TRIGGER " + name + " " + sql


for action in ("INSERT", "UPDATE"):
    guard("console_uart_lab_" + action.lower(), f"""BEFORE {action} ON console_uart_mappings
    WHEN NEW.client_id IS NOT NULL AND
      (SELECT lab_id FROM console_clients WHERE id=NEW.client_id) != (SELECT lab_id FROM suts WHERE id=NEW.sut_id)
    BEGIN SELECT RAISE(ABORT, 'console same-Lab binding required'); END""")
    guard("console_uart_slot_" + action.lower(), f"""BEFORE {action} ON console_uart_mappings
    WHEN NEW.active_slot != CASE WHEN NEW.client_id IS NOT NULL AND
      (SELECT is_archived FROM suts WHERE id=NEW.sut_id)=0 AND
      (SELECT enabled FROM console_clients WHERE id=NEW.client_id)=1 THEN 1 ELSE 0 END
    BEGIN SELECT RAISE(ABORT, 'console active slot inconsistent'); END""")
    guard("console_credential_owner_" + action.lower(), f"""BEFORE {action} ON console_clients
    WHEN NEW.active_credential_id IS NOT NULL AND NOT EXISTS
      (SELECT 1 FROM console_credentials WHERE id=NEW.active_credential_id AND client_security_id=NEW.security_id)
    BEGIN SELECT RAISE(ABORT, 'console credential ownership mismatch'); END""")

guard("console_client_lab", """BEFORE UPDATE OF lab_id ON console_clients
WHEN EXISTS (SELECT 1 FROM console_uart_mappings m JOIN suts s ON s.id=m.sut_id
             WHERE m.client_id=NEW.id AND s.lab_id != NEW.lab_id)
BEGIN SELECT RAISE(ABORT, 'console Client has retained cross-Lab bindings'); END""")
guard("console_sut_lab", """BEFORE UPDATE OF lab_id ON suts
WHEN EXISTS (SELECT 1 FROM console_uart_mappings m JOIN console_clients c ON c.id=m.client_id
             WHERE m.sut_id=NEW.id AND c.lab_id != NEW.lab_id)
BEGIN SELECT RAISE(ABORT, 'console SUT has cross-Lab bindings'); END""")
guard("console_client_slots", """AFTER UPDATE OF enabled ON console_clients
BEGIN UPDATE console_uart_mappings SET active_slot=CASE WHEN NEW.enabled=1 AND
 (SELECT is_archived FROM suts WHERE id=sut_id)=0 THEN 1 ELSE 0 END WHERE client_id=NEW.id; END""")
guard("console_sut_slots", """AFTER UPDATE OF is_archived ON suts
BEGIN UPDATE console_uart_mappings SET active_slot=CASE WHEN NEW.is_archived=0 AND
 (SELECT enabled FROM console_clients WHERE id=client_id)=1 THEN 1 ELSE 0 END WHERE sut_id=NEW.id; END""")
guard("console_grant_creation", """BEFORE UPDATE OF created_at ON console_grants
WHEN NEW.created_at != OLD.created_at BEGIN SELECT RAISE(ABORT, 'console grant creation immutable'); END""")
for table in ("console_mapping_events", "console_audits"):
    for action in ("UPDATE", "DELETE"):
        guard(table + "_" + action.lower(), f"""BEFORE {action} ON {table}
        BEGIN SELECT RAISE(ABORT, 'console history is append-only'); END""")
fields = ("client_id", "bmc_sut_id", "ipv4", "port", "endpoint_epoch", "algorithm", "public_key",
          "fingerprint", "trust_revision", "previous_id", "accepted_by", "created_at")
guard("console_host_key_immutable", "BEFORE UPDATE ON console_host_keys WHEN " +
      " OR ".join("NEW." + f + " IS NOT OLD." + f for f in fields) +
      " OR (OLD.is_current=0 AND NEW.is_current=1) BEGIN SELECT RAISE(ABORT, 'console host key identity immutable'); END")
guard("console_host_key_retention", "BEFORE DELETE ON console_host_keys BEGIN SELECT RAISE(ABORT, 'console host key retained'); END")


def install_guards():
    for sql in GUARDS.values():
        op.execute(sql)
