// ============================================================
//  인식표 정보 수집 — Google Apps Script 백엔드
//  이 파일을 Google Apps Script 편집기에 붙여넣으세요.
// ============================================================

const SHEET_NAME = "인식표 정보";
const HEADER = ["군번", "성명", "혈액형", "RH", "제출시간"];

/** 웹앱 URL 접속 시 폼 HTML 반환 */
function doGet() {
  return HtmlService.createHtmlOutputFromFile("index")
    .setTitle("인식표 정보 입력")
    .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL);
}

/** 폼 제출 처리 — 클라이언트(index.html)에서 호출 */
function submitForm(data) {
  try {
    const sheet = getOrCreateSheet();

    // 유효성 검사
    const BLOOD_TYPES = ["A", "B", "O", "AB"];
    const RH_VALUES = ["RH+", "RH-"];

    if (!data.gunBun || !data.name || !data.bloodType || !data.rh) {
      return { ok: false, message: "모든 항목을 입력해주세요." };
    }
    if (!BLOOD_TYPES.includes(data.bloodType)) {
      return { ok: false, message: "올바른 혈액형을 선택해주세요." };
    }
    if (!RH_VALUES.includes(data.rh)) {
      return { ok: false, message: "RH를 선택해주세요." };
    }

    // 중복 군번 확인
    const lastRow = sheet.getLastRow();
    if (lastRow > 1) {
      const existingIds = sheet
        .getRange(2, 1, lastRow - 1, 1)
        .getValues()
        .map(function (row) { return String(row[0]).trim(); });

      if (existingIds.includes(data.gunBun.trim())) {
        return { ok: false, message: "이미 제출된 군번입니다. 수정이 필요하면 담당자에게 문의하세요." };
      }
    }

    // 데이터 저장
    const timestamp = Utilities.formatDate(
      new Date(),
      "Asia/Seoul",
      "yyyy-MM-dd HH:mm:ss"
    );
    sheet.appendRow([
      data.gunBun.trim(),
      data.name.trim(),
      data.bloodType,
      data.rh,
      timestamp,
    ]);

    return { ok: true };
  } catch (e) {
    return { ok: false, message: "오류가 발생했습니다: " + e.message };
  }
}

/** 시트가 없으면 생성하고 헤더 추가 */
function getOrCreateSheet() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sheet = ss.getSheetByName(SHEET_NAME);

  if (!sheet) {
    sheet = ss.insertSheet(SHEET_NAME);
    sheet.appendRow(HEADER);

    // 헤더 스타일
    const headerRange = sheet.getRange(1, 1, 1, HEADER.length);
    headerRange.setFontWeight("bold");
    headerRange.setBackground("#1a3a5c");
    headerRange.setFontColor("#ffffff");
    sheet.setFrozenRows(1);

    // 열 너비 설정
    sheet.setColumnWidth(1, 130); // 군번
    sheet.setColumnWidth(2, 90);  // 성명
    sheet.setColumnWidth(3, 70);  // 혈액형
    sheet.setColumnWidth(4, 60);  // RH
    sheet.setColumnWidth(5, 170); // 제출시간
  }

  return sheet;
}
