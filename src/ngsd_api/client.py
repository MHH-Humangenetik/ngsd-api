from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, AsyncIterator, cast
from sqlalchemy.ext.asyncio import AsyncConnection

import sqlalchemy as sa
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .config import NgsdSettings
from .types import (
    CodingAnnotation,
    GeneVariant,
    PhenotypeEntry,
    ProcessedSample,
    ReportFinding,
    Run,
    RunStatus,
    SamplePhenotype,
    SampleVariant,
    StructuralVariant,
    Trio,
    VariantCarrier,
    VariantClassification,
)

# Row cap on every read method, keeping large-sample results manageable.
MAX_ROWS = 200

# Range-shaped SV tables sharing one column layout, unlike breakend-shaped
# sv_translocation (chr1/start1/end1/chr2/start2/end2).
_SV_RANGE_TABLES = ("sv_deletion", "sv_duplication", "sv_insertion", "sv_inversion")


@dataclass(frozen=True)
class _ProcessedSample:
    ps_id: int
    processing_system: str
    genome_build: str


def _parse_coding(coding: str | None) -> list[CodingAnnotation]:
    """Parses `variant.coding` (`SYMBOL:ENST...:consequence:IMPACT`, comma-separated).

    There is no variant->gene foreign key in NGSD — this text column is the
    only source of gene/consequence annotation.
    """
    if not coding:
        return []
    annotations = []
    for entry in coding.split(","):
        parts = entry.split(":")
        if len(parts) >= 4:
            annotations.append(
                CodingAnnotation(gene=parts[0], transcript=parts[1], consequence=parts[2], impact=parts[3])
            )
    return annotations


def _class_at_least(acmg_class: str | None, min_class: str) -> bool:
    """Compares ACMG classes '1'-'5' numerically; 'n/a'/'M'/'R' never match."""
    if acmg_class is None or not acmg_class.isdigit() or not min_class.isdigit():
        return False
    return int(acmg_class) >= int(min_class)


async def _resolve_processed_samples(session: AsyncSession, sample_name: str) -> list[_ProcessedSample]:
    """Resolves a sample name to its processed_sample run(s) — a sample can
    have several (re-sequencing, multiple panels)."""
    sql = sa.text(
        "SELECT ps.id, psy.name_short, gn.build "
        "FROM processed_sample ps "
        "JOIN sample s ON s.id = ps.sample_id "
        "JOIN processing_system psy ON psy.id = ps.processing_system_id "
        "JOIN genome gn ON gn.id = psy.genome_id "
        "WHERE s.name = :name"
    )
    rows = (await session.execute(sql, {"name": sample_name})).fetchall()
    if not rows:
        raise ValueError(f"no sample named {sample_name!r}")
    return [_ProcessedSample(ps_id=r[0], processing_system=r[1], genome_build=r[2]) for r in rows]


async def _resolve_variant_id(
    session: AsyncSession, chr: str, start: int, end: int, ref: str, obs: str
) -> int | None:
    sql = sa.text("SELECT id FROM variant WHERE chr = :chr AND start = :start AND end = :end AND ref = :ref AND obs = :obs")
    row = (await session.execute(sql, {"chr": chr, "start": start, "end": end, "ref": ref, "obs": obs})).fetchone()
    return row[0] if row else None


async def _resolve_gene_region(session: AsyncSession, gene_symbol: str) -> tuple[str, int, int]:
    """Resolves a gene symbol to (chr, start, end) via its best transcript.

    Prefers the MANE Select transcript, falling back to the Ensembl canonical
    one. `gene_transcript` coordinates come from the latest Ensembl import and
    are not tagged with a genome build — see NGSD's schema gotchas ("mind the
    sample's genome build" when filtering variants by a resolved region).
    """
    sql = sa.text(
        "SELECT gt.chromosome, gt.start_coding, gt.end_coding "
        "FROM gene g JOIN gene_transcript gt ON gt.gene_id = g.id "
        "WHERE g.symbol = :symbol AND gt.start_coding IS NOT NULL "
        "ORDER BY gt.is_mane_select DESC, gt.is_ensembl_canonical DESC "
        "LIMIT 1"
    )
    row = (await session.execute(sql, {"symbol": gene_symbol})).fetchone()
    if row is None:
        raise ValueError(f"no coding region found for gene {gene_symbol!r}")
    chromosome, start, end = row
    return f"chr{chromosome}", start, end


def _sample_variant_from_row(row: Any, ps_by_id: dict[int, _ProcessedSample]) -> SampleVariant:
    ps = ps_by_id[row[0]]
    return SampleVariant(
        processed_sample_id=row[0],
        processing_system=ps.processing_system,
        genome_build=ps.genome_build,
        chr=row[1],
        start=row[2],
        end=row[3],
        ref=row[4],
        obs=row[5],
        gnomad=row[6],
        cadd=row[7],
        spliceai=row[8],
        genotype=row[9],
        mosaic=bool(row[10]),
        coding=_parse_coding(row[11]),
        acmg_class=row[12],
    )


_SAMPLE_VARIANTS_SQL = (
    "SELECT dv.processed_sample_id, v.chr, v.start, v.end, v.ref, v.obs, "
    "v.gnomad, v.cadd, v.spliceai, dv.genotype, dv.mosaic, v.coding, vc.class "
    "FROM detected_variant dv "
    "JOIN variant v ON v.id = dv.variant_id "
    "LEFT JOIN variant_classification vc ON vc.variant_id = v.id "
    "WHERE dv.processed_sample_id IN :ps_ids "
    "LIMIT :limit"
)


class NgsdApi:
    """Async API client for the NGSD MariaDB database."""

    def __init__(self, settings: NgsdSettings) -> None:
        self._settings = settings
        dsn = f"mysql+aiomysql://{settings.user}:{settings.password}@{settings.host}:{settings.port}/{settings.database}"
        self._engine = create_async_engine(dsn, echo=False)
        self._session_factory = async_sessionmaker(
            self._engine, class_=AsyncSession, expire_on_commit=False
        )
        self._pool_connection: AsyncConnection | None = None

    async def __aenter__(self) -> "NgsdApi":
        self._pool_connection = await self._engine.connect()
        return self

    async def __aexit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        if self._pool_connection is not None:
            await self._pool_connection.close()
        await self._engine.dispose()

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """Provide a transactional scope for database operations."""
        async with self._session_factory() as session:
            yield session

    async def get_runs_by_processing_system(
        self, processing_system_name: str, status: RunStatus | None = None
    ) -> list[Run]:
        """Fetch runs filtered by processing system and optionally by status."""
        sql_parts = [
            "SELECT DISTINCT sr.name, sr.status",
            "FROM sequencing_run sr",
            "INNER JOIN processed_sample ps ON ps.sequencing_run_id = sr.id",
            "INNER JOIN processing_system pss ON pss.id = ps.processing_system_id",
            "WHERE pss.name_short = :processing_system",
        ]
        params: dict[str, str] = {"processing_system": processing_system_name}
        if status is not None:
            sql_parts.append("AND sr.status = :status")
            params["status"] = status.value
        sql = " ".join(sql_parts)
        async with self.session() as session:
            result = await session.execute(sa.text(sql), params)
            rows = result.fetchall()
            return [Run(name=row[0], status=RunStatus(row[1])) for row in rows]

    async def set_run_status_by_name(self, runname: str, status: RunStatus) -> bool:
        """Update the status of a run by name."""
        sql = "UPDATE sequencing_run SET status = :status WHERE name = :name"
        async with self.session() as session:
            result = await session.execute(sa.text(sql), {"name": runname, "status": status.value})
            await session.commit()
            cursor_result = cast(CursorResult[Any], result)
            return cursor_result.rowcount > 0

    async def get_run_by_processed_sample_name(self, processed_sample_name: str) -> Run | None:
        """Resolves a processed sample name (e.g. "307780PR1_03") to its sequencing run.

        A processed sample name is `<sample.name>_<process_id>`, zero-padded
        to 2 digits. Returns `None` if the name doesn't parse as
        `name_id`, or no processed sample/run matches.
        """
        try:
            sample_name, process_id_str = processed_sample_name.rsplit("_", 1)
            process_id = int(process_id_str)
        except ValueError:
            return None

        sql = sa.text(
            "SELECT sr.name, sr.status "
            "FROM sequencing_run sr "
            "JOIN processed_sample ps ON ps.sequencing_run_id = sr.id "
            "JOIN sample s ON s.id = ps.sample_id "
            "WHERE s.name = :sample_name AND ps.process_id = :process_id"
        )
        async with self.session() as session:
            row = (
                await session.execute(sql, {"sample_name": sample_name, "process_id": process_id})
            ).fetchone()
        return Run(name=row[0], status=RunStatus(row[1])) if row else None

    async def get_sample_variants(
        self, sample_name: str, gene: str | None = None, min_acmg_class: str | None = None
    ) -> list[SampleVariant]:
        """Small variants detected in a sample, with ACMG class if known.

        Returns at most `MAX_ROWS` variants per processed_sample run. Raises
        `ValueError` if no sample has this name. `min_acmg_class` keeps only
        classes >= the given one among '1'-'5' ('M'/'R'/'n/a' never match).
        """
        async with self.session() as session:
            samples = await _resolve_processed_samples(session, sample_name)
            ps_by_id = {s.ps_id: s for s in samples}
            sql = sa.text(_SAMPLE_VARIANTS_SQL).bindparams(sa.bindparam("ps_ids", expanding=True))
            rows = (
                await session.execute(sql, {"ps_ids": list(ps_by_id), "limit": MAX_ROWS + 1})
            ).fetchall()
        variants = [_sample_variant_from_row(row, ps_by_id) for row in rows[:MAX_ROWS]]
        if gene is not None:
            variants = [v for v in variants if any(c.gene == gene for c in v.coding)]
        if min_acmg_class is not None:
            variants = [v for v in variants if _class_at_least(v.acmg_class, min_acmg_class)]
        return variants

    async def get_samples_with_variant(
        self, chr: str, start: int, end: int, ref: str, obs: str
    ) -> list[VariantCarrier]:
        """Samples carrying a specific variant, with genotype.

        Coordinates must match NGSD's stored representation exactly (the
        build used when the variant was called) — a build mismatch simply
        returns no results rather than a wrong match.
        """
        async with self.session() as session:
            variant_id = await _resolve_variant_id(session, chr, start, end, ref, obs)
            if variant_id is None:
                return []
            sql = sa.text(
                "SELECT s.name, ps.id, psy.name_short, dv.genotype, dv.mosaic "
                "FROM detected_variant dv "
                "JOIN processed_sample ps ON ps.id = dv.processed_sample_id "
                "JOIN sample s ON s.id = ps.sample_id "
                "JOIN processing_system psy ON psy.id = ps.processing_system_id "
                "WHERE dv.variant_id = :variant_id "
                "LIMIT :limit"
            )
            rows = (await session.execute(sql, {"variant_id": variant_id, "limit": MAX_ROWS + 1})).fetchall()
        return [
            VariantCarrier(sample_name=r[0], processed_sample_id=r[1], processing_system=r[2], genotype=r[3], mosaic=bool(r[4]))
            for r in rows[:MAX_ROWS]
        ]

    async def search_variants_by_gene(
        self, gene_symbol: str, sample_name: str | None = None
    ) -> list[SampleVariant] | list[GeneVariant]:
        """Variants overlapping a gene's coding region.

        If `sample_name` is given, results are bounded by that sample's
        processed_sample_id (safe regardless of sample size) and carry
        genotype/ACMG class. Otherwise this scans `variant` bounded to the
        gene's region across all samples — mind the genome build (NGSD mixes
        builds; region coordinates come from the latest Ensembl import).
        """
        async with self.session() as session:
            if sample_name is not None:
                samples = await _resolve_processed_samples(session, sample_name)
                ps_by_id = {s.ps_id: s for s in samples}
                sql = sa.text(_SAMPLE_VARIANTS_SQL).bindparams(sa.bindparam("ps_ids", expanding=True))
                rows = (
                    await session.execute(sql, {"ps_ids": list(ps_by_id), "limit": MAX_ROWS + 1})
                ).fetchall()
                variants = [_sample_variant_from_row(row, ps_by_id) for row in rows[:MAX_ROWS]]
                return [v for v in variants if any(c.gene == gene_symbol for c in v.coding)]

            chromosome, region_start, region_end = await _resolve_gene_region(session, gene_symbol)
            sql = sa.text(
                "SELECT v.chr, v.start, v.end, v.ref, v.obs, v.gnomad, v.cadd, v.coding "
                "FROM variant v WHERE v.chr = :chr AND v.start BETWEEN :region_start AND :region_end "
                "LIMIT :limit"
            )
            rows = (
                await session.execute(
                    sql,
                    {"chr": chromosome, "region_start": region_start, "region_end": region_end, "limit": MAX_ROWS + 1},
                )
            ).fetchall()
        unscoped = [
            GeneVariant(chr=r[0], start=r[1], end=r[2], ref=r[3], obs=r[4], gnomad=r[5], cadd=r[6], coding=_parse_coding(r[7]))
            for r in rows[:MAX_ROWS]
        ]
        return [v for v in unscoped if any(c.gene == gene_symbol for c in v.coding)]

    async def get_sample_phenotype(self, sample_name: str) -> SamplePhenotype:
        """A sample's disease group/status and HPO/OMIM/Orpha/ICD10 entries.

        Raises `ValueError` if no sample has this name.
        """
        async with self.session() as session:
            sql = sa.text("SELECT id, disease_group, disease_status, gender, tumor FROM sample WHERE name = :name")
            row = (await session.execute(sql, {"name": sample_name})).fetchone()
            if row is None:
                raise ValueError(f"no sample named {sample_name!r}")
            sample_id, disease_group, disease_status, gender, tumor = row

            sql = sa.text(
                "SELECT sdi.type, sdi.disease_info, ht.name "
                "FROM sample_disease_info sdi "
                "LEFT JOIN hpo_term ht ON sdi.type = 'HPO term id' AND ht.hpo_id = sdi.disease_info "
                "WHERE sdi.sample_id = :sample_id"
            )
            entries = [
                PhenotypeEntry(type=r[0], value=r[1], hpo_name=r[2])
                for r in (await session.execute(sql, {"sample_id": sample_id})).fetchall()
            ]
        return SamplePhenotype(
            sample_name=sample_name,
            disease_group=disease_group,
            disease_status=disease_status,
            gender=gender,
            tumor=bool(tumor),
            entries=entries,
        )

    async def get_variant_classification(
        self, chr: str, start: int, end: int, ref: str, obs: str
    ) -> VariantClassification | None:
        """ACMG class, classification rationale, and linked PubMed IDs for a variant.

        Returns `None` if the variant is unknown or unclassified. Coordinates
        must match NGSD's stored representation exactly, same caveat as
        `get_samples_with_variant`.
        """
        async with self.session() as session:
            variant_id = await _resolve_variant_id(session, chr, start, end, ref, obs)
            if variant_id is None:
                return None
            sql = sa.text("SELECT class, comment FROM variant_classification WHERE variant_id = :variant_id")
            row = (await session.execute(sql, {"variant_id": variant_id})).fetchone()
            if row is None:
                return None
            acmg_class, comment = row
            sql = sa.text("SELECT pubmed FROM variant_literature WHERE variant_id = :variant_id")
            pubmed_ids = [r[0] for r in (await session.execute(sql, {"variant_id": variant_id})).fetchall()]
        return VariantClassification(acmg_class=acmg_class, comment=comment, pubmed_ids=pubmed_ids)

    async def get_sample_structural_variants(
        self, sample_name: str, sv_type: str = "all"
    ) -> list[StructuralVariant]:
        """CNVs, SVs, and/or repeat expansions detected in a sample.

        `sv_type` selects `"cnv"`, `"sv"`, `"re"`, or `"all"` (default) — only
        the requested query kinds run. Raises `ValueError` if no sample has
        this name, or if `sv_type` is invalid.
        """
        if sv_type not in ("cnv", "sv", "re", "all"):
            raise ValueError(f"invalid sv_type {sv_type!r}, expected cnv/sv/re/all")
        async with self.session() as session:
            samples = await _resolve_processed_samples(session, sample_name)
            ps_ids = [s.ps_id for s in samples]
            results: list[StructuralVariant] = []

            if sv_type in ("cnv", "all"):
                sql = sa.text(
                    "SELECT cc.processed_sample_id, c.chr, c.start, c.end, c.cn "
                    "FROM cnv_callset cc JOIN cnv c ON c.cnv_callset_id = cc.id "
                    "WHERE cc.processed_sample_id IN :ps_ids LIMIT :limit"
                ).bindparams(sa.bindparam("ps_ids", expanding=True))
                rows = (await session.execute(sql, {"ps_ids": ps_ids, "limit": MAX_ROWS + 1})).fetchall()
                results.extend(
                    StructuralVariant(sv_type="cnv", processed_sample_id=r[0], chr=r[1], start=r[2], end=r[3], cn=r[4])
                    for r in rows[:MAX_ROWS]
                )

            if sv_type in ("sv", "all"):
                for table in _SV_RANGE_TABLES:
                    sql = sa.text(
                        f"SELECT sc.processed_sample_id, sv.chr, sv.start_min, sv.end_max, sv.genotype "
                        f"FROM sv_callset sc JOIN {table} sv ON sv.sv_callset_id = sc.id "
                        f"WHERE sc.processed_sample_id IN :ps_ids LIMIT :limit"
                    ).bindparams(sa.bindparam("ps_ids", expanding=True))
                    rows = (await session.execute(sql, {"ps_ids": ps_ids, "limit": MAX_ROWS + 1})).fetchall()
                    results.extend(
                        StructuralVariant(
                            sv_type=table.removeprefix("sv_"), processed_sample_id=r[0], chr=r[1], start=r[2], end=r[3], genotype=r[4]
                        )
                        for r in rows[:MAX_ROWS]
                    )
                sql = sa.text(
                    "SELECT sc.processed_sample_id, sv.chr1, sv.start1, sv.end1, sv.chr2, sv.start2, sv.end2, sv.genotype "
                    "FROM sv_callset sc JOIN sv_translocation sv ON sv.sv_callset_id = sc.id "
                    "WHERE sc.processed_sample_id IN :ps_ids LIMIT :limit"
                ).bindparams(sa.bindparam("ps_ids", expanding=True))
                rows = (await session.execute(sql, {"ps_ids": ps_ids, "limit": MAX_ROWS + 1})).fetchall()
                results.extend(
                    StructuralVariant(
                        sv_type="translocation", processed_sample_id=r[0],
                        chr=r[1], start=r[2], end=r[3], chr2=r[4], start2=r[5], end2=r[6], genotype=r[7],
                    )
                    for r in rows[:MAX_ROWS]
                )

            if sv_type in ("re", "all"):
                sql = sa.text(
                    "SELECT reg.processed_sample_id, reg.allele1, reg.allele2, re.repeat_unit, re.disease_names "
                    "FROM repeat_expansion_genotype reg "
                    "JOIN repeat_expansion re ON re.id = reg.repeat_expansion_id "
                    "WHERE reg.processed_sample_id IN :ps_ids LIMIT :limit"
                ).bindparams(sa.bindparam("ps_ids", expanding=True))
                rows = (await session.execute(sql, {"ps_ids": ps_ids, "limit": MAX_ROWS + 1})).fetchall()
                results.extend(
                    StructuralVariant(
                        sv_type="re", processed_sample_id=r[0], allele1=r[1], allele2=r[2], repeat_unit=r[3], disease_names=r[4]
                    )
                    for r in rows[:MAX_ROWS]
                )
        return results

    async def get_report_findings(self, sample_name: str) -> list[ReportFinding]:
        """Diagnostic report findings (causal/candidate/incidental) for a sample.

        Raises `ValueError` if no sample has this name.
        """
        async with self.session() as session:
            samples = await _resolve_processed_samples(session, sample_name)
            sql = sa.text(
                "SELECT id FROM report_configuration WHERE processed_sample_id IN :ps_ids"
            ).bindparams(sa.bindparam("ps_ids", expanding=True))
            report_ids = [r[0] for r in (await session.execute(sql, {"ps_ids": [s.ps_id for s in samples]})).fetchall()]
            if not report_ids:
                return []
            report_ids_param = {"report_ids": report_ids}

            findings: list[ReportFinding] = []

            sql = sa.text(
                "SELECT rcv.type, rcv.causal, vc.class, rcv.inheritance, v.chr, v.start, v.end, v.ref, v.obs "
                "FROM report_configuration_variant rcv "
                "JOIN variant v ON v.id = rcv.variant_id "
                "LEFT JOIN variant_classification vc ON vc.variant_id = v.id "
                "WHERE rcv.report_configuration_id IN :report_ids"
            ).bindparams(sa.bindparam("report_ids", expanding=True))
            findings.extend(
                ReportFinding(
                    finding_type="variant", type=r[0], causal=bool(r[1]), acmg_class=r[2], inheritance=r[3],
                    chr=r[4], start=r[5], end=r[6], ref=r[7], obs=r[8],
                )
                for r in (await session.execute(sql, report_ids_param)).fetchall()
            )

            sql = sa.text(
                "SELECT rcc.type, rcc.causal, rcc.class, rcc.inheritance, c.chr, c.start, c.end "
                "FROM report_configuration_cnv rcc "
                "JOIN cnv c ON c.id = rcc.cnv_id "
                "WHERE rcc.report_configuration_id IN :report_ids"
            ).bindparams(sa.bindparam("report_ids", expanding=True))
            findings.extend(
                ReportFinding(
                    finding_type="cnv", type=r[0], causal=bool(r[1]), acmg_class=r[2], inheritance=r[3],
                    chr=r[4], start=r[5], end=r[6],
                )
                for r in (await session.execute(sql, report_ids_param)).fetchall()
            )

            sql = sa.text(
                "SELECT rcs.type, rcs.causal, rcs.class, rcs.inheritance, "
                "COALESCE(d.chr, du.chr, ins.chr, inv.chr, t.chr1) AS chr, "
                "COALESCE(d.start_min, du.start_min, ins.start_min, inv.start_min, t.start1) AS start, "
                "COALESCE(d.end_max, du.end_max, ins.end_max, inv.end_max, t.end1) AS end "
                "FROM report_configuration_sv rcs "
                "LEFT JOIN sv_deletion d ON d.id = rcs.sv_deletion_id "
                "LEFT JOIN sv_duplication du ON du.id = rcs.sv_duplication_id "
                "LEFT JOIN sv_insertion ins ON ins.id = rcs.sv_insertion_id "
                "LEFT JOIN sv_inversion inv ON inv.id = rcs.sv_inversion_id "
                "LEFT JOIN sv_translocation t ON t.id = rcs.sv_translocation_id "
                "WHERE rcs.report_configuration_id IN :report_ids"
            ).bindparams(sa.bindparam("report_ids", expanding=True))
            findings.extend(
                ReportFinding(
                    finding_type="sv", type=r[0], causal=bool(r[1]), acmg_class=r[2], inheritance=r[3],
                    chr=r[4], start=r[5], end=r[6],
                )
                for r in (await session.execute(sql, report_ids_param)).fetchall()
            )

            sql = sa.text(
                "SELECT rcr.type, rcr.causal, rcr.inheritance "
                "FROM report_configuration_re rcr "
                "WHERE rcr.report_configuration_id IN :report_ids"
            ).bindparams(sa.bindparam("report_ids", expanding=True))
            findings.extend(
                ReportFinding(finding_type="re", type=r[0], causal=bool(r[1]), acmg_class=None, inheritance=r[2])
                for r in (await session.execute(sql, report_ids_param)).fetchall()
            )

            sql = sa.text(
                "SELECT type, inheritance, gene, coordinates "
                "FROM report_configuration_other_causal_variant "
                "WHERE report_configuration_id IN :report_ids"
            ).bindparams(sa.bindparam("report_ids", expanding=True))
            findings.extend(
                ReportFinding(
                    finding_type="other", type=r[0], causal=True, acmg_class=None,
                    inheritance=r[1], gene=r[2], coordinates=r[3],
                )
                for r in (await session.execute(sql, report_ids_param)).fetchall()
            )
        return findings

    async def get_trio_by_sample(self, sample_name: str) -> Trio:
        """Get trio (child/father/mother) for a sample via sample_relations.

        Raises `ValueError` if no sample has this name, or if the sample
        does not have exactly one father and one mother.
        """
        async with self.session() as session:
            sql = sa.text("SELECT id FROM sample WHERE name = :name")
            row = (await session.execute(sql, {"name": sample_name})).fetchone()
            if row is None:
                raise ValueError(f"no sample named {sample_name!r}")
            sample_id = row[0]

            sql = sa.text(
                "SELECT s.name, s.gender "
                "FROM sample_relations sr "
                "JOIN sample s ON s.id = sr.sample1_id "
                "WHERE sr.sample2_id = :sample_id AND sr.relation = 'parent-child'"
            )
            parents = (await session.execute(sql, {"sample_id": sample_id})).fetchall()

            if not parents:
                raise ValueError(f"sample {sample_name!r} has no parents")

            father, mother = None, None
            for name, gender in parents:
                if gender == "male":
                    father = name
                elif gender == "female":
                    mother = name

            if father is None:
                raise ValueError(f"sample {sample_name!r} has no father")
            if mother is None:
                raise ValueError(f"sample {sample_name!r} has no mother")

        return Trio(child=sample_name, father=father, mother=mother)

    async def get_processed_sample_folder(self, processed_sample_name: str) -> str:
        """Get the folder path for a processed sample.

        The path is constructed from the project's type and name, or from
        `folder_override` if set. If `projects_base` is configured, it is
        prepended to the path.

        Raises `ValueError` if the processed sample name doesn't parse or
        doesn't exist.
        """
        try:
            sample_name, process_id_str = processed_sample_name.rsplit("_", 1)
            process_id = int(process_id_str)
        except ValueError:
            raise ValueError(f"invalid processed sample name {processed_sample_name!r}")

        async with self.session() as session:
            sql = sa.text(
                "SELECT p.name, p.type, p.folder_override "
                "FROM processed_sample ps "
                "JOIN sample s ON s.id = ps.sample_id "
                "JOIN project p ON p.id = ps.project_id "
                "WHERE s.name = :sample_name AND ps.process_id = :process_id"
            )
            row = (await session.execute(sql, {"sample_name": sample_name, "process_id": process_id})).fetchone()
            if row is None:
                raise ValueError(f"no processed sample named {processed_sample_name!r}")

            project_name, project_type, folder_override = row

        sample_folder = f"Sample_{sample_name}_{process_id:02d}"
        if folder_override:
            path = f"{folder_override}/{sample_folder}"
        else:
            base = self._settings.projects_base or ""
            path = f"{base}/{project_type}/{project_name}/{sample_folder}"

        return path

    async def get_processed_samples_by_sample_name(
        self,
        sample_name: str,
        project: str | None = None,
        processing_system: str | None = None,
    ) -> list[ProcessedSample]:
        """Get all processed samples for a sample, with project and processing system.

        Optionally filter by `project` (project name) and/or `processing_system`
        (processing system short name).

        Raises `ValueError` if no sample has this name.
        """
        async with self.session() as session:
            sql = sa.text("SELECT id FROM sample WHERE name = :name")
            row = (await session.execute(sql, {"name": sample_name})).fetchone()
            if row is None:
                raise ValueError(f"no sample named {sample_name!r}")
            sample_id = row[0]

            sql_parts = [
                "SELECT ps.process_id, p.name, psy.name_short "
                "FROM processed_sample ps "
                "JOIN project p ON p.id = ps.project_id "
                "JOIN processing_system psy ON psy.id = ps.processing_system_id "
                "WHERE ps.sample_id = :sample_id"
            ]
            params: dict[str, str | int] = {"sample_id": sample_id}

            if project is not None:
                sql_parts.append("AND p.name = :project")
                params["project"] = project
            if processing_system is not None:
                sql_parts.append("AND psy.name_short = :processing_system")
                params["processing_system"] = processing_system

            sql_parts.append("ORDER BY ps.process_id")
            sql = sa.text(" ".join(sql_parts))
            rows = (await session.execute(sql, params)).fetchall()

        return [
            ProcessedSample(name=f"{sample_name}_{r[0]:02d}", process_id=r[0], project=r[1], processing_system=r[2])
            for r in rows
        ]

    async def get_trio_by_processed_sample(self, processed_sample_name: str) -> Trio:
        """Get trio (child/father/mother) as processed sample names.

        Finds parents that have processed samples matching the same project
        AND processing system as the input, returning the newest (highest
        process_id) for each family member.

        Raises `ValueError` if the processed sample name doesn't parse,
        doesn't exist, or if a complete trio cannot be found with matching
        project and processing system.
        """
        try:
            sample_name, process_id_str = processed_sample_name.rsplit("_", 1)
            process_id = int(process_id_str)
        except ValueError:
            raise ValueError(f"invalid processed sample name {processed_sample_name!r}")

        async with self.session() as session:
            sql = sa.text(
                "SELECT s.id, p.name, psy.name_short "
                "FROM processed_sample ps "
                "JOIN sample s ON s.id = ps.sample_id "
                "JOIN project p ON p.id = ps.project_id "
                "JOIN processing_system psy ON psy.id = ps.processing_system_id "
                "WHERE s.name = :sample_name AND ps.process_id = :process_id"
            )
            row = (await session.execute(sql, {"sample_name": sample_name, "process_id": process_id})).fetchone()
            if row is None:
                raise ValueError(f"no processed sample named {processed_sample_name!r}")
            child_sample_id, project, processing_system = row

            sql = sa.text(
                "SELECT s.name, s.gender "
                "FROM sample_relations sr "
                "JOIN sample s ON s.id = sr.sample1_id "
                "WHERE sr.sample2_id = :sample_id AND sr.relation = 'parent-child'"
            )
            parents = (await session.execute(sql, {"sample_id": child_sample_id})).fetchall()

            if not parents:
                raise ValueError(f"sample {sample_name!r} has no parents")

            father_sample, mother_sample = None, None
            for name, gender in parents:
                if gender == "male":
                    father_sample = name
                elif gender == "female":
                    mother_sample = name

            if father_sample is None:
                raise ValueError(f"sample {sample_name!r} has no father")
            if mother_sample is None:
                raise ValueError(f"sample {sample_name!r} has no mother")

            sql = sa.text(
                "SELECT s.name, MAX(ps.process_id) "
                "FROM processed_sample ps "
                "JOIN sample s ON s.id = ps.sample_id "
                "JOIN project p ON p.id = ps.project_id "
                "JOIN processing_system psy ON psy.id = ps.processing_system_id "
                "WHERE s.name IN :names AND p.name = :project AND psy.name_short = :processing_system "
                "GROUP BY s.name"
            ).bindparams(sa.bindparam("names", expanding=True))
            rows = (await session.execute(sql, {
                "names": [father_sample, mother_sample],
                "project": project,
                "processing_system": processing_system,
            })).fetchall()

            parent_ps = {r[0]: f"{r[0]}_{r[1]:02d}" for r in rows}

            if father_sample not in parent_ps:
                raise ValueError(
                    f"father {father_sample!r} has no processed sample in project {project!r} "
                    f"with processing system {processing_system!r}"
                )
            if mother_sample not in parent_ps:
                raise ValueError(
                    f"mother {mother_sample!r} has no processed sample in project {project!r} "
                    f"with processing system {processing_system!r}"
                )

        return Trio(child=processed_sample_name, father=parent_ps[father_sample], mother=parent_ps[mother_sample])
