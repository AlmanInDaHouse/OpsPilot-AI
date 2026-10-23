from uuid import UUID, uuid4

from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from opspilot.adapters.postgres.models import GrantRow, PrincipalRow
from opspilot.identity.domain.principal import ExternalIdentity, Principal, Role
from opspilot.shared.errors import DependencyUnavailable


class PostgresPrincipals:
    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self.sessions = sessions

    def find(self, identity: ExternalIdentity) -> Principal | None:
        try:
            with self.sessions() as session:
                # One statement snapshot: identity and grants are never read at different revisions.
                rows = session.execute(
                    select(PrincipalRow.id, PrincipalRow.enabled, GrantRow.role)
                    .outerjoin(
                        GrantRow,
                        (GrantRow.principal_id == PrincipalRow.id) & GrantRow.revoked_at.is_(None),
                    )
                    .where(
                        PrincipalRow.issuer == identity.issuer,
                        PrincipalRow.subject == identity.subject,
                    )
                ).all()
                if not rows:
                    return None
                return Principal(
                    rows[0].id,
                    rows[0].enabled,
                    frozenset(Role(row.role) for row in rows if row.role),
                )
        except SQLAlchemyError as exc:
            raise DependencyUnavailable() from exc


class IdentityWriter:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, issuer: str, subject: str) -> tuple[UUID, bool]:
        row = self.session.execute(
            text("""INSERT INTO principals(id,issuer,subject) VALUES (:id,:iss,:sub)
            ON CONFLICT (issuer,subject) DO NOTHING RETURNING id"""),
            {"id": uuid4(), "iss": issuer, "sub": subject},
        ).scalar_one_or_none()
        if row is not None:
            return row, True
        return self.session.execute(
            select(PrincipalRow.id)
            .where(PrincipalRow.issuer == issuer, PrincipalRow.subject == subject)
            .with_for_update()
        ).scalar_one(), False

    def change(self, principal_id: UUID, action: str, role: Role | None) -> int | None:
        self.session.execute(
            select(PrincipalRow.id).where(PrincipalRow.id == principal_id).with_for_update()
        ).scalar_one()
        if action == "disable":
            changed = self.session.execute(
                text("UPDATE principals SET enabled=false WHERE id=:id AND enabled RETURNING id"),
                {"id": principal_id},
            ).scalar_one_or_none()
            return 1 if changed else None
        if role is None:
            raise ValueError("Explicit role required")
        if action == "grant":
            return self.session.execute(
                text("""INSERT INTO role_grants(principal_id,role) VALUES (:id,:role)
                ON CONFLICT (principal_id,role) DO UPDATE SET revoked_at=NULL,version=role_grants.version+1
                WHERE role_grants.revoked_at IS NOT NULL RETURNING version"""),
                {"id": principal_id, "role": role.value},
            ).scalar_one_or_none()
        if action == "revoke":
            return self.session.execute(
                text("""UPDATE role_grants SET revoked_at=CURRENT_TIMESTAMP,version=version+1
                WHERE principal_id=:id AND role=:role AND revoked_at IS NULL RETURNING version"""),
                {"id": principal_id, "role": role.value},
            ).scalar_one_or_none()
        raise ValueError("Unknown action")
