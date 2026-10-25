import copy

from isis_agent.state import Manifest
from isis_agent.sync import sync_material

from .conftest import fixture

PDF_PATH = "/webservice/pluginfile.php/1/mod_resource/content/1/VL01.pdf"
TXT_PATH = "/webservice/pluginfile.php/1/mod_folder/content/0/boese.txt"


def setup_fake(fake, contents=None):
    fake.responses["core_course_get_contents"] = contents or fixture("course_contents.json")
    fake.files[PDF_PATH] = b"%PDF-fake"
    fake.files[TXT_PATH] = b"hallo"


def test_first_sync_downloads_files_safely(client, fake, kurs, tmp_path):
    setup_fake(fake)
    manifest = Manifest.load(tmp_path / "manifest.json")
    result = sync_material(client, kurs, tmp_path, manifest)

    paths = {str(c.path) for c in result.changes}
    assert paths == {
        "material/01-woche-1-hoerschwelle/VL01_Hörschwelle.pdf",
        "material/01-woche-1-hoerschwelle/uebungsmaterial/Unter/ordner/_.._boese.txt",
    }
    assert all(c.kind == "neu" for c in result.changes)
    for p in paths:
        assert (tmp_path / p).is_file()
    assert result.links[0].url == "https://www.ak.tu-berlin.de/"
    overview = result.overview.read_text(encoding="utf-8")
    assert "Willkommen zur Psychoakustik!" in overview and "Versteckt" not in overview


def test_second_sync_downloads_nothing(client, fake, kurs, tmp_path):
    setup_fake(fake)
    manifest = Manifest(tmp_path / "manifest.json")
    sync_material(client, kurs, tmp_path, manifest)
    manifest.save()
    fake.downloads.clear()

    result = sync_material(client, kurs, tmp_path, Manifest.load(tmp_path / "manifest.json"))
    assert result.changes == [] and result.unchanged == 2
    assert fake.downloads == []


def test_changed_file_is_redownloaded(client, fake, kurs, tmp_path):
    setup_fake(fake)
    manifest = Manifest(tmp_path / "manifest.json")
    sync_material(client, kurs, tmp_path, manifest)

    contents = copy.deepcopy(fixture("course_contents.json"))
    contents[1]["modules"][0]["contents"][0]["timemodified"] += 100
    setup_fake(fake, contents)
    fake.files[PDF_PATH] = b"%PDF-neu"
    result = sync_material(client, kurs, tmp_path, manifest)

    assert [(c.kind, c.path.name) for c in result.changes] == [("geändert", "VL01_Hörschwelle.pdf")]
    assert (tmp_path / result.changes[0].path).read_bytes() == b"%PDF-neu"


def test_missing_local_file_is_restored(client, fake, kurs, tmp_path):
    setup_fake(fake)
    manifest = Manifest(tmp_path / "manifest.json")
    first = sync_material(client, kurs, tmp_path, manifest)
    (tmp_path / first.changes[0].path).unlink()
    result = sync_material(client, kurs, tmp_path, manifest)
    assert len(result.changes) == 1


def test_download_error_is_reported_not_fatal(client, fake, kurs, tmp_path):
    setup_fake(fake)
    del fake.files[TXT_PATH]
    result = sync_material(client, kurs, tmp_path, Manifest(tmp_path / "m.json"))
    assert len(result.changes) == 1 and len(result.errors) == 1
