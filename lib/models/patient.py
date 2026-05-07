from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, List, Optional

from pydantic import BaseModel, Field, model_validator
from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from lib.models.base import Base, PatchModel
from lib.models.evidence_block import EvidenceBlock, HumanEvidenceBlock
from lib.models.family import Family
from lib.models.paper import PaperDB

if TYPE_CHECKING:
    from lib.models.family import FamilyDB
    from lib.models.patient_variant_link import PatientVariantLinkDB
    from lib.models.phenotype import PhenotypeDB


class ProbandStatus(str, Enum):
    Proband = 'Proband'
    Non_proband = 'Non-Proband'
    Unknown = 'Unknown'


class AffectedStatus(str, Enum):
    Affected = 'Affected'
    Unaffected = 'Unaffected'
    Unknown = 'Unknown'


class RelationshipToProband(str, Enum):
    Proband = 'Proband'
    Parent = 'Parent'
    Sibling = 'Sibling'
    Half_Sibling = 'Half-Sibling'
    Child = 'Child'
    Other = 'Other'
    Unknown = 'Unknown'


class TwinType(str, Enum):
    Monozygotic = 'Monozygotic'
    Dizygotic = 'Dizygotic'
    Unknown = 'Unknown'


class AgeUnit(str, Enum):
    Years = 'Years'
    Months = 'Months'
    Days = 'Days'


class SexAtBirth(str, Enum):
    Male = 'Male'
    Female = 'Female'
    Intersex = 'Intersex'
    MTF = 'MTF/Transwoman/Transgender Female'
    FTM = 'FTM/Transman/Transgender Male'
    Ambiguous = 'Ambiguous/Unable to Determine'
    Other = 'Other'
    Unknown = 'Unknown'


class RaceEthnicity(str, Enum):
    African_American = 'African/African American'
    Latino_Admixed_American = 'Latino/Admixed American'
    Ashkenazi_Jewish = 'Ashkenazi Jewish'
    East_Asian = 'East Asian'
    Finnish = 'Finnish'
    Non_Finnish_European = 'Non-Finnish European'
    South_Asian = 'South Asian'
    Middle_Eastern = 'Middle Eastern'
    Amish = 'Amish'
    Other = 'Other'
    Unknown = 'Unknown'


class CountryCode(str, Enum):
    Afghanistan = 'Afghanistan'
    Åland_Islands = 'Åland Islands'
    Albania = 'Albania'
    Algeria = 'Algeria'
    American_Samoa = 'American Samoa'
    Andorra = 'Andorra'
    Angola = 'Angola'
    Anguilla = 'Anguilla'
    Antarctica = 'Antarctica'
    Antigua_and_Barbuda = 'Antigua and Barbuda'
    Argentina = 'Argentina'
    Armenia = 'Armenia'
    Aruba = 'Aruba'
    Australia = 'Australia'
    Austria = 'Austria'
    Azerbaijan = 'Azerbaijan'
    Bahamas = 'Bahamas'
    Bahrain = 'Bahrain'
    Bangladesh = 'Bangladesh'
    Barbados = 'Barbados'
    Belarus = 'Belarus'
    Belgium = 'Belgium'
    Belize = 'Belize'
    Benin = 'Benin'
    Bermuda = 'Bermuda'
    Bhutan = 'Bhutan'
    Bolivia_Plurinational_State_of = 'Bolivia, Plurinational State of'
    Bonaire_Sint_Eustatius_and_Saba = 'Bonaire, Sint Eustatius and Saba'
    Bosnia_and_Herzegovina = 'Bosnia and Herzegovina'
    Botswana = 'Botswana'
    Bouvet_Island = 'Bouvet Island'
    Brazil = 'Brazil'
    British_Indian_Ocean_Territory = 'British Indian Ocean Territory'
    Brunei_Darussalam = 'Brunei Darussalam'
    Bulgaria = 'Bulgaria'
    Burkina_Faso = 'Burkina Faso'
    Burundi = 'Burundi'
    Cambodia = 'Cambodia'
    Cameroon = 'Cameroon'
    Canada = 'Canada'
    Cape_Verde = 'Cape Verde'
    Cayman_Islands = 'Cayman Islands'
    Central_African_Republic = 'Central African Republic'
    Chad = 'Chad'
    Chile = 'Chile'
    China = 'China'
    Christmas_Island = 'Christmas Island'
    Cocos_Keeling_Islands = 'Cocos (Keeling) Islands'
    Colombia = 'Colombia'
    Comoros = 'Comoros'
    Congo = 'Congo'
    Congo_Democratic_Republic_of_the = 'Congo, the Democratic Republic of the'
    Cook_Islands = 'Cook Islands'
    Costa_Rica = 'Costa Rica'
    Cote_dIvoire = "Côte d'Ivoire"
    Croatia = 'Croatia'
    Cuba = 'Cuba'
    Curaçao = 'Curaçao'
    Cyprus = 'Cyprus'
    Czech_Republic = 'Czech Republic'
    Denmark = 'Denmark'
    Djibouti = 'Djibouti'
    Dominica = 'Dominica'
    Dominican_Republic = 'Dominican Republic'
    Ecuador = 'Ecuador'
    Egypt = 'Egypt'
    El_Salvador = 'El Salvador'
    Equatorial_Guinea = 'Equatorial Guinea'
    Eritrea = 'Eritrea'
    Estonia = 'Estonia'
    Ethiopia = 'Ethiopia'
    Falkland_Islands_Malvinas = 'Falkland Islands (Malvinas)'
    Faroe_Islands = 'Faroe Islands'
    Fiji = 'Fiji'
    Finland = 'Finland'
    France = 'France'
    French_Guiana = 'French Guiana'
    French_Polynesia = 'French Polynesia'
    French_Southern_Territories = 'French Southern Territories'
    Gabon = 'Gabon'
    Gambia = 'Gambia'
    Georgia = 'Georgia'
    Germany = 'Germany'
    Ghana = 'Ghana'
    Gibraltar = 'Gibraltar'
    Greece = 'Greece'
    Greenland = 'Greenland'
    Grenada = 'Grenada'
    Guadeloupe = 'Guadeloupe'
    Guam = 'Guam'
    Guatemala = 'Guatemala'
    Guernsey = 'Guernsey'
    Guinea = 'Guinea'
    Guinea_Bissau = 'Guinea-Bissau'
    Guyana = 'Guyana'
    Haiti = 'Haiti'
    Heard_Island_and_McDonald_Islands = 'Heard Island and McDonald Islands'
    Holy_See_Vatican_City_State = 'Holy See (Vatican City State)'
    Honduras = 'Honduras'
    Hong_Kong = 'Hong Kong'
    Hungary = 'Hungary'
    Iceland = 'Iceland'
    India = 'India'
    Indonesia = 'Indonesia'
    Iran_Islamic_Republic_of = 'Iran, Islamic Republic of'
    Iraq = 'Iraq'
    Ireland = 'Ireland'
    Isle_of_Man = 'Isle of Man'
    Israel = 'Israel'
    Italy = 'Italy'
    Jamaica = 'Jamaica'
    Japan = 'Japan'
    Jersey = 'Jersey'
    Jordan = 'Jordan'
    Kazakhstan = 'Kazakhstan'
    Kenya = 'Kenya'
    Kiribati = 'Kiribati'
    Korea_Democratic_Peoples_Republic_of = "Korea, Democratic People's Republic of"
    Korea_Republic_of = 'Korea, Republic of'
    Kuwait = 'Kuwait'
    Kyrgyzstan = 'Kyrgyzstan'
    Lao_Peoples_Democratic_Republic = "Lao People's Democratic Republic"
    Latvia = 'Latvia'
    Lebanon = 'Lebanon'
    Lesotho = 'Lesotho'
    Liberia = 'Liberia'
    Libya = 'Libya'
    Liechtenstein = 'Liechtenstein'
    Lithuania = 'Lithuania'
    Luxembourg = 'Luxembourg'
    Macao = 'Macao'
    Macedonia_the_former_Yugoslav_Republic_of = (
        'Macedonia, the former Yugoslav Republic of'
    )
    Madagascar = 'Madagascar'
    Malawi = 'Malawi'
    Malaysia = 'Malaysia'
    Maldives = 'Maldives'
    Mali = 'Mali'
    Malta = 'Malta'
    Marshall_Islands = 'Marshall Islands'
    Martinique = 'Martinique'
    Mauritania = 'Mauritania'
    Mauritius = 'Mauritius'
    Mayotte = 'Mayotte'
    Mexico = 'Mexico'
    Micronesia_Federated_States_of = 'Micronesia, Federated States of'
    Moldova_Republic_of = 'Moldova, Republic of'
    Monaco = 'Monaco'
    Mongolia = 'Mongolia'
    Montenegro = 'Montenegro'
    Montserrat = 'Montserrat'
    Morocco = 'Morocco'
    Mozambique = 'Mozambique'
    Myanmar = 'Myanmar'
    Namibia = 'Namibia'
    Nauru = 'Nauru'
    Nepal = 'Nepal'
    Netherlands = 'Netherlands'
    New_Caledonia = 'New Caledonia'
    New_Zealand = 'New Zealand'
    Nicaragua = 'Nicaragua'
    Niger = 'Niger'
    Nigeria = 'Nigeria'
    Niue = 'Niue'
    Norfolk_Island = 'Norfolk Island'
    Northern_Mariana_Islands = 'Northern Mariana Islands'
    Norway = 'Norway'
    Oman = 'Oman'
    Pakistan = 'Pakistan'
    Palau = 'Palau'
    Palestinian_Territory_Occupied = 'Palestinian Territory, Occupied'
    Panama = 'Panama'
    Papua_New_Guinea = 'Papua New Guinea'
    Paraguay = 'Paraguay'
    Peru = 'Peru'
    Philippines = 'Philippines'
    Pitcairn = 'Pitcairn'
    Poland = 'Poland'
    Portugal = 'Portugal'
    Puerto_Rico = 'Puerto Rico'
    Qatar = 'Qatar'
    Réunion = 'Réunion'
    Romania = 'Romania'
    Russian_Federation = 'Russian Federation'
    Rwanda = 'Rwanda'
    Saint_Barthélemy = 'Saint Barthélemy'
    Saint_Helena_Ascension_and_Tristan_da_Cunha = (
        'Saint Helena, Ascension and Tristan da Cunha'
    )
    Saint_Kitts_and_Nevis = 'Saint Kitts and Nevis'
    Saint_Lucia = 'Saint Lucia'
    Saint_Martin_French_part = 'Saint Martin (French part)'
    Saint_Pierre_and_Miquelon = 'Saint Pierre and Miquelon'
    Saint_Vincent_and_the_Grenadines = 'Saint Vincent and the Grenadines'
    Samoa = 'Samoa'
    San_Marino = 'San Marino'
    Sao_Tome_and_Principe = 'Sao Tome and Principe'
    Saudi_Arabia = 'Saudi Arabia'
    Senegal = 'Senegal'
    Serbia = 'Serbia'
    Seychelles = 'Seychelles'
    Sierra_Leone = 'Sierra Leone'
    Singapore = 'Singapore'
    Sint_Maarten_Dutch_part = 'Sint Maarten (Dutch part)'
    Slovakia = 'Slovakia'
    Slovenia = 'Slovenia'
    Solomon_Islands = 'Solomon Islands'
    Somalia = 'Somalia'
    South_Africa = 'South Africa'
    South_Georgia_and_the_South_Sandwich_Islands = (
        'South Georgia and the South Sandwich Islands'
    )
    South_Sudan = 'South Sudan'
    Spain = 'Spain'
    Sri_Lanka = 'Sri Lanka'
    Sudan = 'Sudan'
    Suriname = 'Suriname'
    Svalbard_and_Jan_Mayen = 'Svalbard and Jan Mayen'
    Swaziland = 'Swaziland'
    Sweden = 'Sweden'
    Switzerland = 'Switzerland'
    Syrian_Arab_Republic = 'Syrian Arab Republic'
    Taiwan_Province_of_China = 'Taiwan, Province of China'
    Tajikistan = 'Tajikistan'
    Tanzania_United_Republic_of = 'Tanzania, United Republic of'
    Thailand = 'Thailand'
    Timor_Leste = 'Timor-Leste'
    Togo = 'Togo'
    Tokelau = 'Tokelau'
    Tonga = 'Tonga'
    Trinidad_and_Tobago = 'Trinidad and Tobago'
    Tunisia = 'Tunisia'
    Turkey = 'Turkey'
    Turkmenistan = 'Turkmenistan'
    Turks_and_Caicos_Islands = 'Turks and Caicos Islands'
    Tuvalu = 'Tuvalu'
    Uganda = 'Uganda'
    Ukraine = 'Ukraine'
    United_Arab_Emirates = 'United Arab Emirates'
    United_Kingdom = 'United Kingdom'
    United_States = 'United States'
    United_States_Minor_Outlying_Islands = 'United States Minor Outlying Islands'
    Uruguay = 'Uruguay'
    Uzbekistan = 'Uzbekistan'
    Vanuatu = 'Vanuatu'
    Venezuela_Bolivarian_Republic_of = 'Venezuela, Bolivarian Republic of'
    Vietnam = 'Vietnam'
    Virgin_Islands_British = 'Virgin Islands, British'
    Virgin_Islands_US = 'Virgin Islands, U.S.'
    Wallis_and_Futuna = 'Wallis and Futuna'
    Western_Sahara = 'Western Sahara'
    Yemen = 'Yemen'
    Zambia = 'Zambia'
    Zimbabwe = 'Zimbabwe'
    Other = 'Other'
    Unknown = 'Unknown'


class Patient(BaseModel):
    identifier: EvidenceBlock[str]
    family_identifier: EvidenceBlock[str]
    proband_status: EvidenceBlock[ProbandStatus]
    sex: EvidenceBlock[SexAtBirth]
    age_diagnosis: EvidenceBlock[int | None]
    age_diagnosis_unit: AgeUnit | None = None
    age_report: EvidenceBlock[int | None]
    age_report_unit: AgeUnit | None = None
    age_death: EvidenceBlock[int | None]
    age_death_unit: AgeUnit | None = None
    country_of_origin: EvidenceBlock[CountryCode]
    race_ethnicity: EvidenceBlock[RaceEthnicity]
    affected_status: EvidenceBlock[AffectedStatus]
    is_obligate_carrier: EvidenceBlock[bool] = Field(
        default_factory=lambda: EvidenceBlock(
            value=False, reasoning='Not indicated as obligate carrier'
        )
    )
    relationship_to_proband: EvidenceBlock[RelationshipToProband] = Field(
        default_factory=lambda: EvidenceBlock(
            value=RelationshipToProband.Unknown, reasoning='Relationship not specified'
        )
    )
    twin_type: EvidenceBlock[TwinType | None] = Field(
        default_factory=lambda: EvidenceBlock[TwinType | None](
            value=None, reasoning='Twin status not specified'
        )
    )

    @model_validator(mode='after')
    def validate_age_units(self) -> 'Patient':
        """Ensure age fields and their units are both populated or both null."""
        age_pairs = [
            ('age_diagnosis', 'age_diagnosis_unit'),
            ('age_report', 'age_report_unit'),
            ('age_death', 'age_death_unit'),
        ]
        for age_field, unit_field in age_pairs:
            age_value = getattr(self, age_field).value
            unit_value = getattr(self, unit_field)
            if (age_value is None) != (unit_value is None):
                raise ValueError(
                    f'{age_field} and {unit_field} must both be populated or both null'
                )
        return self


class FamilyEntry(BaseModel):
    """Family grouping with references to patients by their identifier."""

    family: Family
    patient_identifiers: List[EvidenceBlock[str]]


class PatientExtractionOutput(BaseModel):
    patients: List[Patient]
    families: List[FamilyEntry]

    @model_validator(mode='after')
    def validate_family_coverage(self) -> 'PatientExtractionOutput':
        """Ensure every patient is assigned to exactly one family."""
        patient_identifiers = {p.identifier.value for p in self.patients}
        assigned_identifiers: set[str] = set()
        for entry in self.families:
            assigned_identifiers.update(
                id_block.value for id_block in entry.patient_identifiers
            )

        missing = patient_identifiers - assigned_identifiers
        if missing:
            raise ValueError(f'Patients not assigned to any family: {missing}')

        extra = assigned_identifiers - patient_identifiers
        if extra:
            raise ValueError(
                f'Family assignments reference non-existent patients: {extra}'
            )

        return self


class PatientDB(Base):
    __tablename__ = 'patients'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    paper_id: Mapped[int] = mapped_column(
        Integer, ForeignKey('papers.id', ondelete='CASCADE'), nullable=False
    )
    family_id: Mapped[int] = mapped_column(
        Integer, ForeignKey('families.id', ondelete='CASCADE'), nullable=False
    )

    # Extracted values (updateable, strongly typed)
    identifier: Mapped[str] = mapped_column(String, nullable=False)
    proband_status: Mapped[str] = mapped_column(String, nullable=False)
    sex: Mapped[str] = mapped_column(String, nullable=False)
    age_diagnosis: Mapped[int | None] = mapped_column(Integer, nullable=True)
    age_diagnosis_unit: Mapped[AgeUnit | None] = mapped_column(
        SQLEnum(AgeUnit), nullable=True
    )
    age_report: Mapped[int | None] = mapped_column(Integer, nullable=True)
    age_report_unit: Mapped[AgeUnit | None] = mapped_column(
        SQLEnum(AgeUnit), nullable=True
    )
    age_death: Mapped[int | None] = mapped_column(Integer, nullable=True)
    age_death_unit: Mapped[AgeUnit | None] = mapped_column(
        SQLEnum(AgeUnit), nullable=True
    )
    country_of_origin: Mapped[str] = mapped_column(String, nullable=False)
    race_ethnicity: Mapped[str] = mapped_column(String, nullable=False)
    affected_status: Mapped[str] = mapped_column(String, nullable=False)
    is_obligate_carrier: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    relationship_to_proband: Mapped[str | None] = mapped_column(String, nullable=True)
    twin_type: Mapped[str | None] = mapped_column(String, nullable=True)

    # Evidence blocks (static, immutable)
    identifier_evidence: Mapped[dict] = mapped_column(JSON, nullable=False)
    proband_status_evidence: Mapped[dict] = mapped_column(JSON, nullable=False)
    sex_evidence: Mapped[dict] = mapped_column(JSON, nullable=False)
    age_diagnosis_evidence: Mapped[dict] = mapped_column(JSON, nullable=False)
    age_report_evidence: Mapped[dict] = mapped_column(JSON, nullable=False)
    age_death_evidence: Mapped[dict] = mapped_column(JSON, nullable=False)
    country_of_origin_evidence: Mapped[dict] = mapped_column(JSON, nullable=False)
    race_ethnicity_evidence: Mapped[dict] = mapped_column(JSON, nullable=False)
    affected_status_evidence: Mapped[dict] = mapped_column(JSON, nullable=False)
    is_obligate_carrier_evidence: Mapped[dict | None] = mapped_column(
        JSON, nullable=True
    )
    relationship_to_proband_evidence: Mapped[dict | None] = mapped_column(
        JSON, nullable=True
    )
    twin_type_evidence: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    family_assignment_evidence: Mapped[dict] = mapped_column(JSON, nullable=False)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    paper: Mapped[PaperDB] = relationship('PaperDB', back_populates='patients')
    family: Mapped['FamilyDB'] = relationship('FamilyDB', back_populates='patients')
    phenotypes: Mapped[list['PhenotypeDB']] = relationship(
        'PhenotypeDB', back_populates='patient', cascade='all, delete-orphan'
    )
    patient_variant_links: Mapped[list['PatientVariantLinkDB']] = relationship(
        'PatientVariantLinkDB', back_populates='patient', cascade='all, delete-orphan'
    )

    __table_args__ = (
        Index('ix_patients_paper_id', 'paper_id'),
        Index('ix_patients_family_id', 'family_id'),
    )


class PatientResp(BaseModel):
    id: int
    paper_id: int
    identifier: str
    proband_status: ProbandStatus
    sex: SexAtBirth
    age_diagnosis: int | None
    age_diagnosis_unit: AgeUnit | None = None
    age_report: int | None
    age_report_unit: AgeUnit | None = None
    age_death: int | None
    age_death_unit: AgeUnit | None = None
    country_of_origin: CountryCode
    race_ethnicity: RaceEthnicity
    affected_status: AffectedStatus
    is_obligate_carrier: bool | None
    relationship_to_proband: RelationshipToProband | None
    twin_type: TwinType | None
    updated_at: datetime
    # Evidence blocks (from DB JSON columns)
    identifier_evidence: HumanEvidenceBlock[str]
    proband_status_evidence: HumanEvidenceBlock[ProbandStatus]
    sex_evidence: HumanEvidenceBlock[SexAtBirth]
    age_diagnosis_evidence: HumanEvidenceBlock[int | None]
    age_report_evidence: HumanEvidenceBlock[int | None]
    age_death_evidence: HumanEvidenceBlock[int | None]
    country_of_origin_evidence: HumanEvidenceBlock[CountryCode]
    race_ethnicity_evidence: HumanEvidenceBlock[RaceEthnicity]
    affected_status_evidence: HumanEvidenceBlock[AffectedStatus]
    is_obligate_carrier_evidence: HumanEvidenceBlock[bool] | None
    relationship_to_proband_evidence: HumanEvidenceBlock[RelationshipToProband] | None
    twin_type_evidence: HumanEvidenceBlock[TwinType | None] | None
    family_id: int
    family_identifier: str
    family_assignment_evidence: HumanEvidenceBlock[str]


class PatientCreateRequest(BaseModel):
    identifier: str
    proband_status: str
    sex: str
    age_diagnosis: int | None = None
    age_diagnosis_unit: str | None = None
    age_report: int | None = None
    age_report_unit: str | None = None
    age_death: int | None = None
    age_death_unit: str | None = None
    country_of_origin: str
    race_ethnicity: str
    affected_status: str
    family_id: int


class PatientUpdateRequest(PatchModel):
    identifier: str | None = None
    proband_status: str | None = None
    affected_status: str | None = None
    sex: str | None = None
    age_diagnosis: int | None = None
    age_diagnosis_unit: str | None = None
    age_report: int | None = None
    age_report_unit: str | None = None
    age_death: int | None = None
    age_death_unit: str | None = None
    country_of_origin: str | None = None
    race_ethnicity: str | None = None
    is_obligate_carrier: bool | None = None
    relationship_to_proband: str | None = None
    twin_type: str | None = None
    # Human edit notes for evidence blocks
    identifier_human_edit_note: str | None = None
    proband_status_human_edit_note: str | None = None
    sex_human_edit_note: str | None = None
    age_diagnosis_human_edit_note: str | None = None
    age_report_human_edit_note: str | None = None
    age_death_human_edit_note: str | None = None
    country_of_origin_human_edit_note: str | None = None
    race_ethnicity_human_edit_note: str | None = None
    affected_status_human_edit_note: str | None = None
    is_obligate_carrier_human_edit_note: str | None = None
    relationship_to_proband_human_edit_note: str | None = None
    twin_type_human_edit_note: str | None = None
