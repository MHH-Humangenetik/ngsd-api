from dataclasses import dataclass, field
from enum import Enum


class RunStatus(str, Enum):
    NA = "n/a"
    RUN_STARTED = "run_started"
    RUN_FINISHED = "run_finished"
    RUN_ABORTED = "run_aborted"
    DEMULTIPLEXING_STARTED = "demultiplexing_started"
    ANALYSIS_STARTED = "analysis_started"
    ANALYSIS_FINISHED = "analysis_finished"
    ANALYSIS_NOT_POSSIBLE = "analysis_not_possible"
    ANALYSIS_AND_BACKUP_NOT_REQUIRED = "analysis_and_backup_not_required"


@dataclass(frozen=True)
class Run:
    """Represents a run in the NGSD database."""

    name: str
    status: RunStatus


@dataclass(frozen=True)
class CodingAnnotation:
    """One gene/transcript annotation parsed out of `variant.coding`."""

    gene: str
    transcript: str
    consequence: str
    impact: str


@dataclass(frozen=True)
class SampleVariant:
    """A small variant detected in one processed sample.

    `genome_build` is the build of that processed_sample's processing
    system (e.g. 'GRCh37', 'GRCh38', 'hg19') — NGSD mixes builds across
    samples, so this is needed to interpret `chr`/`start`/`end` correctly
    when a sample has runs on more than one build.
    """

    processed_sample_id: int
    processing_system: str
    genome_build: str
    chr: str
    start: int
    end: int
    ref: str
    obs: str
    genotype: str
    mosaic: bool
    gnomad: float | None
    cadd: float | None
    spliceai: float | None
    acmg_class: str | None
    coding: list[CodingAnnotation] = field(default_factory=list)


@dataclass(frozen=True)
class GeneVariant:
    """A variant in a gene's region, not scoped to any sample."""

    chr: str
    start: int
    end: int
    ref: str
    obs: str
    gnomad: float | None
    cadd: float | None
    coding: list[CodingAnnotation] = field(default_factory=list)


@dataclass(frozen=True)
class VariantCarrier:
    """A sample carrying a specific variant."""

    sample_name: str
    processed_sample_id: int
    processing_system: str
    genotype: str
    mosaic: bool


@dataclass(frozen=True)
class PhenotypeEntry:
    """One phenotype/diagnosis record for a sample."""

    type: str
    value: str
    hpo_name: str | None = None


@dataclass(frozen=True)
class SamplePhenotype:
    """A sample's phenotype/diagnosis information."""

    sample_name: str
    disease_group: str | None
    disease_status: str | None
    gender: str | None
    tumor: bool
    entries: list[PhenotypeEntry] = field(default_factory=list)


@dataclass(frozen=True)
class VariantClassification:
    """ACMG classification of a variant."""

    acmg_class: str
    comment: str | None
    pubmed_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class StructuralVariant:
    """A CNV, SV, or repeat expansion detected in one processed sample.

    Shape varies by `sv_type`: range-based (cnv/deletion/duplication/
    insertion/inversion) uses chr/start/end; translocation additionally
    uses chr2/start2/end2 for the second breakend; repeat expansion uses
    repeat_unit/allele1/allele2 instead of coordinates.
    """

    sv_type: str
    processed_sample_id: int
    chr: str | None = None
    start: int | None = None
    end: int | None = None
    chr2: str | None = None
    start2: int | None = None
    end2: int | None = None
    genotype: str | None = None
    cn: int | None = None
    repeat_unit: str | None = None
    allele1: int | None = None
    allele2: int | None = None
    disease_names: str | None = None


@dataclass(frozen=True)
class ReportFinding:
    """One diagnostic report finding for a sample."""

    finding_type: str  # "variant" | "cnv" | "sv" | "re" | "other"
    type: str  # e.g. "diagnostic variant" | "candidate variant" | "incidental finding"
    causal: bool
    acmg_class: str | None
    inheritance: str | None
    gene: str | None = None
    chr: str | None = None
    start: int | None = None
    end: int | None = None
    ref: str | None = None
    obs: str | None = None
    coordinates: str | None = None


@dataclass(frozen=True)
class Trio:
    """A family trio: child with parents."""

    child: str
    father: str
    mother: str


@dataclass(frozen=True)
class ProcessedSample:
    """A processed sample with its project and processing system."""

    name: str
    process_id: int
    project: str
    processing_system: str
