from enum import Enum
from typing import List, Optional

from agents import Agent, ModelSettings
from pydantic import BaseModel

from lib.evagg.utils.environment import env


class SequencingMethod(str, Enum):
    Chromosomal_Microarray = 'Chromosomal microarray'
    Denaturing_Gradient_Gel = 'Denaturing gradient gel'
    Exome_Sequencing = 'Exome sequencing'
    Genotyping = 'Genotyping'
    High_Resolution_Melting = 'High resolution melting'
    Homozygosity_Mapping = 'Homozygosity mapping'
    Linkage_Analysis = 'Linkage analysis'
    Next_Generation_Sequencing_Panels = 'Next generation sequencing panels'
    PCR = 'PCR'
    Restriction_Digest = 'Restriction digest'
    Sanger_Sequencing = 'Sanger sequencing'
    SSCP = 'SSCP'
    Whole_Genome_Shotgun_Sequencing = 'Whole genome shotgun sequencing'
    Other = 'Other'
    Unknown = 'Unknown'


class SexAtBirth(str, Enum):
    No_Selection = 'No Selection'
    Male = 'Male'
    Female = 'Female'
    Intersex = 'Intersex'
    Mtf = 'MTF/Transwoman/Transgender Female'
    Ftm = 'FTM/Transman/Transgender Male'
    Ambiguous = 'Ambiguous'
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
    Viet_Nam = 'Viet Nam'
    Virgin_Islands_British = 'Virgin Islands, British'
    Virgin_Islands_US = 'Virgin Islands, U.S.'
    Wallis_and_Futuna = 'Wallis and Futuna'
    Western_Sahara = 'Western Sahara'
    Yemen = 'Yemen'
    Zambia = 'Zambia'
    Zimbabwe = 'Zimbabwe'
    Other = 'Other'
    Unknown = 'Unknown'


# --- Patient model


class PatientInfo(BaseModel):
    # Core patient fields
    identifier: str  # Required
    sex: SexAtBirth
    age_diagnosis: Optional[str]  # exact text from source
    age_report: Optional[str]
    age_death: Optional[str]
    country_of_origin: CountryCode
    race_ethnicity: RaceEthnicity

    # Evidence for each field
    identifier_evidence: Optional[str]
    sex_evidence: Optional[str]
    age_diagnosis_evidence: Optional[str]
    age_report_evidence: Optional[str]
    age_death_evidence: Optional[str]
    country_of_origin_evidence: Optional[str]
    race_ethnicity_evidence: Optional[str]


# --- Output wrapper


class PatientInfoExtractionOutput(BaseModel):
    patients: List[PatientInfo]


# --- Instructions for agent

PATIENT_EXTRACTION_INSTRUCTIONS = """
System: You are an expert clinical data curator.

Inputs:
- Text of a paper, case report, or patient registry entry

Task: Extract patient-level demographic information for each proband described.

Fields to extract:
- identifier: Unique identifier for the patient (e.g., Patient 1, II-2, I-1, II6, proband, mother, father)
- sex: Use enum: No Selection, Male, Female, Intersex, MTF/Transwoman/Transgender Female, FTM/Transman/Transgender Male, Ambiguous, Other, Unknown
- Age: capture age at diagnosis, at report, and at death if available; keep as text
- country_of_origin: Use enum values: Afghanistan, Åland Islands, Albania, Algeria, American Samoa, Andorra, Angola, Anguilla, Antarctica, Antigua and Barbuda, Argentina, Armenia, Aruba, Australia, Austria, Azerbaijan, Bahamas, Bahrain, Bangladesh, Barbados, Belarus, Belgium, Belize, Benin, Bermuda, Bhutan, Bolivia, Plurinational State of, Bonaire, Sint Eustatius and Saba, Bosnia and Herzegovina, Botswana, Bouvet Island, Brazil, British Indian Ocean Territory, Brunei Darussalam, Bulgaria, Burkina Faso, Burundi, Cambodia, Cameroon, Canada, Cape Verde, Cayman Islands, Central African Republic, Chad, Chile, China, Christmas Island, Cocos (Keeling) Islands, Colombia, Comoros, Congo, Congo, the Democratic Republic of the, Cook Islands, Costa Rica, Côte d'Ivoire, Croatia, Cuba, Curaçao, Cyprus, Czech Republic, Denmark, Djibouti, Dominica, Dominican Republic, Ecuador, Egypt, El Salvador, Equatorial Guinea, Eritrea, Estonia, Ethiopia, Falkland Islands (Malvinas), Faroe Islands, Fiji, Finland, France, French Guiana, French Polynesia, French Southern Territories, Gabon, Gambia, Georgia, Germany, Ghana, Gibraltar, Greece, Greenland, Grenada, Guadeloupe, Guam, Guatemala, Guernsey, Guinea, Guinea-Bissau, Guyana, Haiti, Heard Island and McDonald Islands, Holy See (Vatican City State), Honduras, Hong Kong, Hungary, Iceland, India, Indonesia, Iran, Islamic Republic of, Iraq, Ireland, Isle of Man, Israel, Italy, Jamaica, Japan, Jersey, Jordan, Kazakhstan, Kenya, Kiribati, Korea, Democratic People's Republic of, Korea, Republic of, Kuwait, Kyrgyzstan, Lao People's Democratic Republic, Latvia, Lebanon, Lesotho, Liberia, Libya, Liechtenstein, Lithuania, Luxembourg, Macao, Macedonia, the former Yugoslav Republic of, Madagascar, Malawi, Malaysia, Maldives, Mali, Malta, Marshall Islands, Martinique, Mauritania, Mauritius, Mayotte, Mexico, Micronesia, Federated States of, Moldova, Republic of, Monaco, Mongolia, Montenegro, Montserrat, Morocco, Mozambique, Myanmar, Namibia, Nauru, Nepal, Netherlands, New Caledonia, New Zealand, Nicaragua, Niger, Nigeria, Niue, Norfolk Island, Northern Mariana Islands, Norway, Oman, Pakistan, Palau, Palestinian Territory, Occupied, Panama, Papua New Guinea, Paraguay, Peru, Philippines, Pitcairn, Poland, Portugal, Puerto Rico, Qatar, Réunion, Romania, Russian Federation, Rwanda, Saint Barthélemy, Saint Helena, Ascension and Tristan da Cunha, Saint Kitts and Nevis, Saint Lucia, Saint Martin (French part), Saint Pierre and Miquelon, Saint Vincent and the Grenadines, Samoa, San Marino, Sao Tome and Principe, Saudi Arabia, Senegal, Serbia, Seychelles, Sierra Leone, Singapore, Sint Maarten (Dutch part), Slovakia, Slovenia, Solomon Islands, Somalia, South Africa, South Georgia and the South Sandwich Islands, South Sudan, Spain, Sri Lanka, Sudan, Suriname, Svalbard and Jan Mayen, Swaziland, Sweden, Switzerland, Syrian Arab Republic, Taiwan, Province of China, Tajikistan, Tanzania, United Republic of, Thailand, Timor-Leste, Togo, Tokelau, Tonga, Trinidad and Tobago, Tunisia, Turkey, Turkmenistan, Turks and Caicos Islands, Tuvalu, Uganda, Ukraine, United Arab Emirates, United Kingdom, United States, United States Minor Outlying Islands, Uruguay, Uzbekistan, Vanuatu, Venezuela, Bolivarian Republic of, Viet Nam, Virgin Islands, British, Virgin Islands, U.S., Wallis and Futuna, Western Sahara, Yemen, Zambia, Zimbabwe, Other, Unknown
- race/ethnicity: Use enum values: African/African American, Latino/Admixed American, Ashkenazi Jewish, East Asian, Finnish, Non-Finnish European, South Asian, Middle Eastern, Amish, Other, Unknown

Guidelines:
1. Extract only explicitly stated information.
2. Preserve original wording for age and country.
3. Use enum values when possible; otherwise, return unknown/Other.
4. Provide exact evidence text for each field.  If citing a figure, in addition to the raw text
also include the title and an interpretable explanation of why the text was cited.
5. Return null for any missing fields.
6. Each patient must have a identifier; if not stated, skip that patient.
7. If no specific human patients are identified, or you are uncertain, simply provide "unknown" as your response.
8. In text patients are often described using adjectives, e.g., "proband's affected sister". In these cases, just respond
with a simplified version of the patient, e.g., "sister".
9. Some papers, specifically case reports will be talking about just one patient. In this case, simply provide "patient" as
your response. In these cases do not add additional text in your response beyond "patient".
10. Occassionally, strings of digits are used as patient identifiers, e.g., "34" or "75987", but it is often difficult to
differentiate these patient identifiers from other strings of digits within a text, so I specifically do not want you
to return these identifiers. In these cases it is better to omit them (if there are others to report) or report 
"unknown" as the sole patient identifier.

Output:
- Use enum values when possible.
- If the text explicitly indicates a value that does not match any predefined enum category, use "Other".
- If the text explicitly states that the value is unknown, ambiguous, or cannot be determined, use "Unknown".
- If the field is completely missing or not mentioned in the source text, return null.
"""

# --- Agent definition

agent = Agent(
    name='patient_info_extractor',
    instructions=PATIENT_EXTRACTION_INSTRUCTIONS,
    model=env.OPENAI_API_DEPLOYMENT,
    output_type=PatientInfoExtractionOutput,
)
