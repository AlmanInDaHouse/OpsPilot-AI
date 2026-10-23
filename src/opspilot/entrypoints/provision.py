"""Privileged local CLI: explicit grants and changes with transactional audit."""

import argparse
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from opspilot.adapters.postgres.audit import PostgresAppender
from opspilot.adapters.postgres.database import PostgresUow, make_engine
from opspilot.adapters.postgres.identity import IdentityWriter
from opspilot.identity.application.provision import change_identity, create_identity
from opspilot.identity.domain.principal import Role


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["create", "grant", "revoke", "disable"])
    parser.add_argument("--dsn-file", type=Path, required=True)
    parser.add_argument("--issuer")
    parser.add_argument("--subject")
    parser.add_argument("--principal-id", type=UUID)
    parser.add_argument("--role", type=Role, choices=list(Role))
    args = parser.parse_args()
    dsn = args.dsn_file.read_text(encoding="utf-8").strip()
    if make_url(dsn).username != "opspilot_provisioner":
        parser.error("Dedicated provisioner role required")
    engine = make_engine(dsn)
    try:
        with PostgresUow(sessionmaker(engine)) as uow:
            writer, audit = IdentityWriter(uow.session), PostgresAppender(uow.session)
            if args.action == "create":
                if not args.issuer or not args.subject:
                    parser.error("create requires issuer and subject")
                principal_id = create_identity(
                    writer, audit, args.issuer, args.subject, uuid4().hex
                )
            else:
                if not args.principal_id or (args.action != "disable" and not args.role):
                    parser.error("Explicit principal and role required")
                principal_id = args.principal_id
                change_identity(writer, audit, principal_id, args.action, args.role, uuid4().hex)
            uow.commit()
        print(principal_id)
        return 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
