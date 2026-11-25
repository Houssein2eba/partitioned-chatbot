from openpyxl import Workbook

from app.rag.loaders import SUPPORTED_EXTENSIONS, load_text


def test_xlsx_loader_extracts_nonempty_rows_by_sheet(tmp_path):
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Summary"
    worksheet.append(["Name", "Value"])
    worksheet.append(["Revenue", 125])
    worksheet.append([None, None])
    second_sheet = workbook.create_sheet("Notes")
    second_sheet.append(["Reviewed"])
    path = tmp_path / "report.xlsx"
    workbook.save(path)

    text = load_text(path)

    assert ".xlsx" in SUPPORTED_EXTENSIONS
    assert "Summary\nName | Value\nRevenue | 125" in text
    assert "Notes\nReviewed" in text
    assert "None" not in text
