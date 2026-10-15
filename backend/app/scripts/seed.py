"""Idempotent synthetic inventory only; never creates accounts or credentials."""

from sqlalchemy import select

from app.core.config import Settings
from app.core.database import make_engine, unit_of_work
from app.models.domain import Lab, SUT


def main():
    settings = Settings()
    if settings.app_env != "development":
        raise SystemExit("Seed is development-only; set APP_ENV=development explicitly")
    engine = make_engine(settings.database_url)
    try:
        with unit_of_work(engine, write=True) as db:
            for number in (1, 2):
                name = f"Demo Taiwan Lab {number}"
                lab = db.scalar(select(Lab).where(Lab.name == name))
                if lab is None:
                    lab = Lab(
                        name=name, location="Synthetic example", description="Fictional development data"
                    )
                    db.add(lab)
                    db.flush()
                for index in range(1, 11):
                    sut_name = f"Demo-SUT-{index}"
                    if not db.scalar(
                        select(SUT.id).where(SUT.lab_id == lab.id, SUT.normalized_name == sut_name.casefold())
                    ):
                        db.add(
                            SUT(
                                lab_id=lab.id,
                                name=sut_name,
                                normalized_name=sut_name.casefold(),
                                platform="Demo platform",
                                owner_team="Demo team",
                                description="Synthetic inventory; no hardware connection",
                            )
                        )
    finally:
        engine.dispose()
    print("Synthetic inventory prepared (2 labs, 20 SUTs); no accounts created.")


if __name__ == "__main__":
    main()
