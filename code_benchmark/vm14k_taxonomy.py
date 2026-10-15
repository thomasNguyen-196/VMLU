"""VM14K specialty taxonomy: medical_topic tags -> coarse categories.

Single source of truth for every consumer (adapter manifest, dashboard
builder, tests). Rule (reviewed 2026-09-22): the category of a row is the
mapping of its PRIMARY tag (first element of `medical_topic`); rows whose
primary tag is missing/junk fall in the explicit "unknown" bucket (same
convention as the frozen MC runner's subject split).

Spelling variants are normalized to the canonical tag before mapping
(e.g. "Infection Diseases" -> "Infectious Diseases"); source rows are never
rewritten — normalization lives only in this mapping.
"""

from __future__ import annotations

CATEGORY_ORDER = [
    "Nội khoa",
    "Sản – Nhi",
    "Ngoại – Gây mê – Hồi sức – Cấp cứu",
    "Dược – Độc – Điều trị",
    "Chuyên khoa khác",
    "Cận lâm sàng & Chẩn đoán",
    "Khoa học cơ sở",
    "Ung bướu & Chăm sóc giảm nhẹ",
    "Y tế công cộng & Dự phòng",
    "unknown",
]

UNKNOWN = "unknown"

# Canonical tag -> category. Every tag observed in the shuffled0 source as of
# 2026-09-22 is listed (133 distinct tags); anything else -> "unknown".
TAG_TO_CATEGORY: dict[str, str] = {
    # ── Nội khoa ──
    "Gastroenterology": "Nội khoa",
    "Pulmonology": "Nội khoa",
    "Endocrinology": "Nội khoa",
    "Cardiology": "Nội khoa",
    "Nephrology": "Nội khoa",
    "Neurology": "Nội khoa",
    "Hematology": "Nội khoa",
    "Rheumatology": "Nội khoa",
    "Allergy and Immunology": "Nội khoa",
    "Geriatrics": "Nội khoa",
    "Hepatology": "Nội khoa",
    "Internal Medicine": "Nội khoa",
    "General Medicine": "Nội khoa",
    "Family Medicine": "Nội khoa",
    "Infectious Diseases": "Nội khoa",
    "Infection Diseases": "Nội khoa",  # spelling variant of Infectious Diseases
    "Virology": "Nội khoa",
    "Hypertension": "Nội khoa",
    "Vascular Medicine": "Nội khoa",
    "Interventional Cardiology": "Nội khoa",
    "Electrocardiography": "Nội khoa",
    # ── Sản – Nhi ──
    "Obstetrics and Gynecology": "Sản – Nhi",
    "Pediatrics": "Sản – Nhi",
    "Neonatology": "Sản – Nhi",
    "Embryology": "Sản – Nhi",
    "Reproductive Medicine": "Sản – Nhi",
    "Family Planning": "Sản – Nhi",
    "Teratology": "Sản – Nhi",
    # ── Ngoại – Gây mê – Hồi sức – Cấp cứu ──
    "Surgery": "Ngoại – Gây mê – Hồi sức – Cấp cứu",
    "Orthopedics": "Ngoại – Gây mê – Hồi sức – Cấp cứu",
    "Urology": "Ngoại – Gây mê – Hồi sức – Cấp cứu",
    "Neurosurgery": "Ngoại – Gây mê – Hồi sức – Cấp cứu",
    "Vascular Surgery": "Ngoại – Gây mê – Hồi sức – Cấp cứu",
    "Anesthesiology": "Ngoại – Gây mê – Hồi sức – Cấp cứu",
    "Pain Management": "Ngoại – Gây mê – Hồi sức – Cấp cứu",
    "Pain Medicine": "Ngoại – Gây mê – Hồi sức – Cấp cứu",
    "Otolaryngology": "Ngoại – Gây mê – Hồi sức – Cấp cứu",
    "Audiology": "Ngoại – Gây mê – Hồi sức – Cấp cứu",
    "Speech-Language Pathology": "Ngoại – Gây mê – Hồi sức – Cấp cứu",
    "Ophthalmology": "Ngoại – Gây mê – Hồi sức – Cấp cứu",
    "Dentistry": "Ngoại – Gây mê – Hồi sức – Cấp cứu",
    "Endodontics": "Ngoại – Gây mê – Hồi sức – Cấp cứu",
    "Periodontology": "Ngoại – Gây mê – Hồi sức – Cấp cứu",
    "Periodontics": "Ngoại – Gây mê – Hồi sức – Cấp cứu",  # variant of Periodontology
    "General Dentistry": "Ngoại – Gây mê – Hồi sức – Cấp cứu",
    "Prosthodontics": "Ngoại – Gây mê – Hồi sức – Cấp cứu",
    "Oral and Maxillofacial Surgery": "Ngoại – Gây mê – Hồi sức – Cấp cứu",
    "Transplant": "Ngoại – Gây mê – Hồi sức – Cấp cứu",
    "Critical Care": "Ngoại – Gây mê – Hồi sức – Cấp cứu",
    "Intensive Care": "Ngoại – Gây mê – Hồi sức – Cấp cứu",
    "Intensive Care Medicine": "Ngoại – Gây mê – Hồi sức – Cấp cứu",
    "Emergency Medicine": "Ngoại – Gây mê – Hồi sức – Cấp cứu",
    "Accident and Emergency": "Ngoại – Gây mê – Hồi sức – Cấp cứu",
    # ── Dược – Độc – Điều trị ──
    "Pharmacology": "Dược – Độc – Điều trị",
    "Pharmaceutical": "Dược – Độc – Điều trị",
    "Pharmacognosy": "Dược – Độc – Điều trị",
    "Toxicology": "Dược – Độc – Điều trị",
    "Medical Toxicology": "Dược – Độc – Điều trị",
    "Addiction Medicine": "Dược – Độc – Điều trị",
    "FDA": "Dược – Độc – Điều trị",
    # ── Chuyên khoa khác ──
    "Psychiatry": "Chuyên khoa khác",
    "Dermatology": "Chuyên khoa khác",
    "Eastern Medicine": "Chuyên khoa khác",
    "Physical Medicine and Rehabilitation": "Chuyên khoa khác",
    "Sports Medicine": "Chuyên khoa khác",
    "Veterinary Medicine": "Chuyên khoa khác",
    # ── Cận lâm sàng & Chẩn đoán ──
    "Radiology": "Cận lâm sàng & Chẩn đoán",
    "Pathology": "Cận lâm sàng & Chẩn đoán",
    "Laboratory Medicine": "Cận lâm sàng & Chẩn đoán",
    "Nuclear Medicine": "Cận lâm sàng & Chẩn đoán",
    "Microbiology": "Cận lâm sàng & Chẩn đoán",
    "Medical Microbiology": "Cận lâm sàng & Chẩn đoán",
    "Parasitology": "Cận lâm sàng & Chẩn đoán",
    "Histology": "Cận lâm sàng & Chẩn đoán",
    "Transfusion Medicine": "Cận lâm sàng & Chẩn đoán",
    "Diagnostic Medicine": "Cận lâm sàng & Chẩn đoán",
    "Diagnostic Testing": "Cận lâm sàng & Chẩn đoán",
    "Diagnosis": "Cận lâm sàng & Chẩn đoán",
    "Physical Examination": "Cận lâm sàng & Chẩn đoán",
    "Forensic Medicine": "Cận lâm sàng & Chẩn đoán",
    # ── Khoa học cơ sở ──
    "Anatomy": "Khoa học cơ sở",
    "Physiology": "Khoa học cơ sở",
    "Biochemistry": "Khoa học cơ sở",
    "Cell Biology": "Khoa học cơ sở",
    "Cellular Biology": "Khoa học cơ sở",  # variant of Cell Biology
    "Molecular Biology": "Khoa học cơ sở",
    "Genetics": "Khoa học cơ sở",
    "Medical Genetics": "Khoa học cơ sở",
    "Genetic": "Khoa học cơ sở",
    "Genetic Disorders": "Khoa học cơ sở",
    "Genetic Engineering": "Khoa học cơ sở",
    "Chemistry": "Khoa học cơ sở",
    "Analytical Chemistry": "Khoa học cơ sở",
    "Industrial Chemistry": "Khoa học cơ sở",
    "Physics": "Khoa học cơ sở",
    "Botany": "Khoa học cơ sở",
    "Entomology": "Khoa học cơ sở",
    "Immunology": "Khoa học cơ sở",
    "Etiology": "Khoa học cơ sở",
    "Clinical Research": "Khoa học cơ sở",
    "Research": "Khoa học cơ sở",
    # ── Ung bướu & Chăm sóc giảm nhẹ ──
    "Oncology": "Ung bướu & Chăm sóc giảm nhẹ",
    "Palliative Medicine": "Ung bướu & Chăm sóc giảm nhẹ",
    # ── Y tế công cộng & Dự phòng ──
    "Public Health": "Y tế công cộng & Dự phòng",
    "Preventive Healthcare": "Y tế công cộng & Dự phòng",
    "Preventive Medicine": "Y tế công cộng & Dự phòng",
    "Epidemiology": "Y tế công cộng & Dự phòng",
    "Environmental Health": "Y tế công cộng & Dự phòng",
    "Occupational Medicine": "Y tế công cộng & Dự phòng",
    "Occupational Health": "Y tế công cộng & Dự phòng",
    "Nutrition": "Y tế công cộng & Dự phòng",
    "Nursing": "Y tế công cộng & Dự phòng",
    "Health Management": "Y tế công cộng & Dự phòng",
    "Health Policy": "Y tế công cộng & Dự phòng",
    "Health System": "Y tế công cộng & Dự phòng",
    "Health Administration": "Y tế công cộng & Dự phòng",
    "Health Economics": "Y tế công cộng & Dự phòng",
    "Demographics": "Y tế công cộng & Dự phòng",
    "Infection Control": "Y tế công cộng & Dự phòng",
    "Patient Safety": "Y tế công cộng & Dự phòng",
    "Risk Assessment": "Y tế công cộng & Dự phòng",
    "Communication Skills": "Y tế công cộng & Dự phòng",
    "Medical Ethics": "Y tế công cộng & Dự phòng",
    "Sociology": "Y tế công cộng & Dự phòng",
    "History of Medicine": "Y tế công cộng & Dự phòng",
}


def primary_topic(topics: object) -> str:
    """First tag of medical_topic, or "" when missing/empty."""
    if isinstance(topics, list) and topics and isinstance(topics[0], str):
        return topics[0]
    return ""


def category_of(topics: object) -> str:
    """Coarse category for a source row's medical_topic list."""
    return TAG_TO_CATEGORY.get(primary_topic(topics), UNKNOWN)
