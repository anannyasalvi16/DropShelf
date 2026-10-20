"""
Unit tests for dropshelf.rules.
"""

import pytest
from dropshelf.config import get_default_rules
from dropshelf.rules import destination_for


@pytest.fixture
def rules():
    return get_default_rules()


def test_each_default_type_maps_correctly(rules):
    # Documents
    assert destination_for("notes.pdf", rules) == "Documents"
    assert destination_for("resume.docx", rules) == "Documents"
    assert destination_for("todo.txt", rules) == "Documents"

    # Spreadsheets
    assert destination_for("budget.xlsx", rules) == "Spreadsheets"
    assert destination_for("data.csv", rules) == "Spreadsheets"

    # Presentations
    assert destination_for("slides.pptx", rules) == "Presentations"

    # Images
    assert destination_for("photo.jpg", rules) == "Images"
    assert destination_for("logo.png", rules) == "Images"
    assert destination_for("diagram.svg", rules) == "Images"

    # Videos
    assert destination_for("movie.mp4", rules) == "Videos"
    assert destination_for("recording.mkv", rules) == "Videos"

    # Audio
    assert destination_for("song.mp3", rules) == "Audio"
    assert destination_for("podcast.wav", rules) == "Audio"

    # Archives
    assert destination_for("archive.zip", rules) == "Archives"
    assert destination_for("backup.tar", rules) == "Archives"

    # Installers
    assert destination_for("setup.exe", rules) == "Installers"
    assert destination_for("package.msi", rules) == "Installers"


def test_uppercase_extensions(rules):
    assert destination_for("DOCUMENT.PDF", rules) == "Documents"
    assert destination_for("PHOTO.PNG", rules) == "Images"
    assert destination_for("ARCHIVE.ZIP", rules) == "Archives"
    assert destination_for("INSTALLER.EXE", rules) == "Installers"


def test_custom_rule_beats_type_rule(rules):
    # In default rules: {"contains": "invoice", "folder": "Finance/Invoices"}
    # A PDF with 'invoice' in its name should go to 'Finance/Invoices', NOT 'Documents'
    assert destination_for("Invoice_2026_01.pdf", rules) == "Finance/Invoices"
    assert destination_for("client_invoice.docx", rules) == "Finance/Invoices"
    assert destination_for("my_invoice_details.txt", rules) == "Finance/Invoices"


def test_custom_rule_order_precedence():
    custom_rules = {
        "custom_rules": [
            {"contains": "Urgent", "folder": "HighPriority"},
            {"contains": "Project", "folder": "Work/Project"},
        ],
        "type_rules": {"Documents": ["pdf"]},
        "fallback_folder": "Other",
        "ignore_extensions": ["tmp"],
    }
    # First match in custom_rules wins
    assert destination_for("Urgent_Project_Plan.pdf", custom_rules) == "HighPriority"
    assert destination_for("Project_Draft.pdf", custom_rules) == "Work/Project"


def test_unknown_extension_goes_to_fallback(rules):
    assert destination_for("unknown.xyz", rules) == "Other"
    assert destination_for("database.dat", rules) == "Other"
    assert destination_for("unknown.unknownext", rules) == "Other"


def test_temp_extensions_return_none(rules):
    assert destination_for("large_video.mp4.crdownload", rules) is None
    assert destination_for("file.part", rules) is None
    assert destination_for("scratch.tmp", rules) is None
    assert destination_for("setup.exe.download", rules) is None
    assert destination_for("opera_dl.opdownload", rules) is None
    assert destination_for("FILE.CRDOWNLOAD", rules) is None


def test_file_with_no_extension(rules):
    assert destination_for("README", rules) == "Other"
    assert destination_for("LICENSE", rules) == "Other"
    assert destination_for("Makefile", rules) == "Other"


def test_custom_rule_on_file_with_no_extension():
    rules = {
        "custom_rules": [
            {"contains": "DOCKER", "folder": "DevOps"},
        ],
        "type_rules": {},
        "fallback_folder": "Other",
        "ignore_extensions": [],
    }
    assert destination_for("Dockerfile", rules) == "DevOps"
