from typing import Mapping


def w2_intake_question() -> str:
    return (
        "Let's build a 2025 federal Form 1040 demo from one fake W-2. "
        "Upload the sample W-2 or choose the sample file to begin."
    )


def filing_status_question() -> str:
    return "I found the fake W-2. What filing status should I use for this demo return?"


def household_question() -> str:
    return "Any household details to note for the demo, such as no dependents?"


def digital_assets_question() -> str:
    return "For the 2025 Form 1040 digital assets question, should I mark yes or no?"


def refund_question() -> str:
    return "How should the demo handle any refund: paper check or fake direct deposit?"


def complete_message(summary: Mapping[str, object]) -> str:
    refund = int(summary.get("refund") or 0)
    owed = int(summary.get("amount_owed") or 0)
    outcome = f"estimated refund is ${refund:,}" if refund else f"estimated amount owed is ${owed:,}"
    return (
        f"Your hackathon demo Form 1040 PDF is ready. The {outcome}. "
        "This is not tax advice, and this prototype cannot e-file, mail, or submit a return."
    )


def refusal_message(code: str) -> str:
    if code == "e_filing":
        return (
            "I can't e-file or submit anything. I can keep helping with this fake 2025 "
            "federal Form 1040 demo."
        )
    if code == "state_return":
        return (
            "I can only help with this fake federal 2025 Form 1040 demo, not state returns. "
            "Let's stay with the federal prototype."
        )
    if code == "real_identity_data":
        return (
            "Please do not share real identity details here. This prototype only uses fake sample data "
            "for a 2025 federal Form 1040 demo."
        )
    return (
        "That is outside this prototype's scope. I can help with one fake W-2 and a 2025 "
        "federal Form 1040 demo."
    )


def retry_message(phase: str) -> str:
    messages = {
        "need_w2": w2_intake_question(),
        "need_filing_status": "Please choose one supported filing status for the demo.",
        "need_household": household_question(),
        "need_digital_assets": "Please answer yes or no for digital assets.",
        "need_refund": "Please choose paper check or fake direct deposit for the demo refund section.",
        "complete": "The demo return is already complete.",
    }
    return messages.get(phase, w2_intake_question())
