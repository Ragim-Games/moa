# 모아 · 나의 위시 저금통

Python으로 만든 **데스크톱 저금통 앱**입니다. 밝은 배경, 둥근 카드, 파란 강조색과 여백으로 Apple·토스에서 영감을 받은 화면을 구성했습니다. Apple 또는 토스의 공식 앱이나 제휴 서비스는 아닙니다.

## 빠른 실행

Python 3.10 이상이 필요합니다. Windows의 python.org 기본 설치에는 GUI용 Tkinter가 포함됩니다. Windows에서 개발·검증했으며 macOS/Linux에서는 별도 실행 검증을 하지 않았습니다. Linux에서는 배포판의 `python3-tk` 및 한글 폰트가 필요할 수 있습니다.

압축을 풀고 `moa` 폴더에서 터미널을 열어 실행하세요.

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python app.py
```

macOS/Linux:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python app.py
```

첫 설치에는 인터넷이 필요합니다. 설치 후에는 오프라인에서도 기록 기능을 사용할 수 있습니다. 앱에는 실제 송금·입금·계좌 연동 기능이 없습니다.

## Windows EXE 빌드

Windows에서 **PyInstaller**로 빌드합니다. 결과물을 실행하는 PC에는 Python을 따로 설치하지 않아도 됩니다. 아래 명령은 `app.py`가 있는 `moa` 폴더의 PowerShell에서 실행하세요. 설치된 Python 버전은 사용하려는 PyInstaller가 지원해야 합니다. 최신 Python에서 설치 오류가 나면 지원되는 버전으로 가상환경을 새로 만드세요.

### 1. 빌드 도구 준비

이미 `.venv`를 만들었다면 첫 줄은 생략합니다.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install --upgrade pyinstaller
```

### 2. 폴더형 EXE 만들기 · 권장

```powershell
.\.venv\Scripts\python.exe -m PyInstaller --clean --onedir --windowed --contents-directory . --name Moa app.py
```

빌드가 끝나면 **`dist\Moa\Moa.exe`**를 실행하세요. `--windowed`는 콘솔 창을 숨기고, `--contents-directory .`는 실행 파일과 지원 파일을 같은 폴더에 배치합니다. 이 배치에서는 현재 소스의 기본 DB 경로가 `dist\Moa\data\moa.sqlite3`가 됩니다. [PyInstaller 옵션 설명](https://pyinstaller.org/en/stable/usage.html)

- 배포할 때는 **`dist\Moa` 폴더 전체**를 압축하세요. EXE만 복사하면 실행에 필요한 파일이 빠집니다.
- 압축을 푼 뒤 `Moa.exe`를 더블클릭하면 됩니다. 데이터 저장을 위해 사용자가 쓸 수 있는 폴더에 두세요.
- 이미 사용 중인 `dist\Moa`를 다시 빌드 대상으로 쓰기 전에는 DB를 백업하세요. 빌드 도구가 기존 출력 폴더를 교체할 수 있습니다.
- 기존 Python 실행 기록을 옮기려면 앱을 모두 종료한 뒤 기존 `data\moa.sqlite3`를 EXE 옆 `data` 폴더에 복사하세요. 다른 사람에게 배포할 때는 개인 기록이 담긴 `data` 폴더를 제외하세요.

### 3. 단일 EXE 만들기 · 데이터 경로 지정 필수

```powershell
.\.venv\Scripts\python.exe -m PyInstaller --clean --onefile --windowed --name MoaSingle app.py
.\dist\MoaSingle.exe --data "$env:LOCALAPPDATA\Moa\moa.sqlite3"
```

결과물은 **`dist\MoaSingle.exe`**입니다. 위 실행 명령은 DB를 `%LOCALAPPDATA%\Moa\moa.sqlite3`에 저장합니다. 필요한 폴더는 앱이 생성합니다.

**현재 소스에서는 단일 EXE를 인수 없이 더블클릭하지 마세요.** 기본 데이터 경로가 `__file__` 기준이라서, `--onefile`에서는 임시 압축 해제 폴더에 DB가 생기고 종료 후 사라질 수 있습니다. 반드시 위처럼 `--data`로 영구 저장 경로를 지정하세요. 더블클릭으로 쓰려면 EXE 바로가기를 만든 뒤, 바로가기 속성의 **대상** 뒤에 `--data "C:\실제\저장폴더\moa.sqlite3"`를 추가하세요. [PyInstaller 실행 경로 설명](https://pyinstaller.org/en/stable/runtime-information.html)

### 아이콘과 오류 확인

실행 파일 아이콘을 바꾸려면 `.ico` 파일을 준비하고 빌드 명령에 `--icon "moa.ico"`를 추가하세요. 이는 EXE 아이콘이며 앱 안에서 선택하는 저금통 아이콘과는 별개입니다. 기본 소스에는 `.ico` 파일이 포함되어 있지 않습니다.

EXE가 바로 종료되어 오류 내용을 볼 수 없다면 콘솔이 표시되는 진단용 빌드를 만드세요.

```powershell
.\.venv\Scripts\python.exe -m PyInstaller --clean --onedir --console --contents-directory . --name MoaDebug app.py
.\dist\MoaDebug\MoaDebug.exe
```

빌드 후 저금통 생성 → 금액 기록 → 앱 종료 → 재실행 순서로 데이터가 유지되는지 확인하고, 가격·환율 조회도 확인하세요. 이 절은 빌드 안내이며, 제공된 검증 결과는 Python 소스 실행 기준입니다. EXE 빌드 및 배포본 실행은 별도로 검증하지 않았습니다.

## 사용 방법

1. **새 저금통**: 이름을 입력하고 16개 아이콘 중 선택합니다. 이모지나 짧은 글자를 직접 입력할 수도 있습니다. 여러 저금통을 만들 수 있습니다.
2. **상품 추가**: 상품명과 URL을 입력하고 `자동 추적`을 선택합니다. 저금통 하나에 여러 상품을 등록할 수 있습니다.
3. **가격 확인**: 시작 시, 상품 저장 시, `가격 새로고침` 버튼을 누를 때 조회합니다. 앱이 실행 중이면 기본 30분마다 전체 저금통의 상품을 확인합니다.
4. **저금 기록 / 출금 기록**: 금융 앱에서 실제로 옮긴 돈을 기록합니다. 저금통별 기록은 분리되며, 잔액보다 많이 출금할 수 없습니다.
5. **잔액 수정**: 현재 실제 잔액을 입력합니다. 차액이 기록에 남습니다. 0원으로 수정하는 것도 가능합니다.
6. **기록 보기 / 가격 기록**: 최근 입출금 및 조회된 가격·환율 기록을 확인합니다.

여러 상품은 **각각 1개씩 모두 구입하는 목표**로 합산합니다. 예를 들어 30만 원과 20만 원 상품을 담고 35만 원을 모았다면 `아직 150,000원 남았어요.`를 표시합니다. 한 상품이라도 가격을 모르면 전체 목표 달성을 확정하지 않습니다. 상품을 사거나 더 이상 목표로 삼지 않으면 목록에서 삭제하고 실제 사용한 돈은 출금으로 기록하세요.

## 자동 가격 추적의 범위

임의의 모든 쇼핑몰을 완벽하게 추적하는 범용 서비스는 아닙니다. 다음과 같이 **서버가 보내는 HTML에 공개된 가격**을 읽습니다.

- Schema.org `Product`의 `offers.price`와 `priceCurrency`
- `AggregateOffer.lowPrice`: **옵션 최저가**라고 명시합니다. 원하는 특정 옵션 가격과 다를 수 있습니다.
- `product:price:amount/currency` 또는 `og:price:amount/currency` 메타데이터
- 사용자가 지정한 **CSS 선택자**의 텍스트 또는 `content` 속성

여러 상품·판매가격이 섞여 있으면 임의로 가장 싼 값을 선택하지 않고 오류를 표시합니다. 통화가 없는 자동 가격은 원화라고 추정하지 않습니다. 원하는 상품·옵션의 단일 가격 요소와 통화를 지정하거나 직접 입력하세요.

로그인, CAPTCHA, 접근 차단, JavaScript 실행 후에만 보이는 가격, 회원·쿠폰·카드 조건부 할인 등은 지원하지 않을 수 있습니다. 자동 조회를 우회하지 않습니다. 지원되지 않는 판매처는 **직접 입력** 모드를 사용하세요. 직접 입력한 외화 가격도 환율을 조회해 원화로 표시합니다. URL을 남기면 `상품 보기`로 직접 확인할 수 있습니다.

고급 사용자는 예를 들어 `.sale-price`와 같은 CSS 선택자를 지정할 수 있습니다. 선택자는 정확히 한 요소를 가리켜야 하며, 원가·할인가·할부 개월 수 등이 함께 들어 있는 영역을 선택하면 오류가 날 수 있습니다. 판매처 HTML이 바뀌면 선택자를 수정해야 합니다. 선택자를 지정할 때는 통화 코드를 직접 확인하세요.

테스트용 공개 사이트 예:

```text
상품명: A Light in the Attic (연습용 상품)
URL: https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html
가격 확인 방식: 자동 추적
통화: GBP
CSS 선택자: .price_color
```

이 사이트는 스크래핑 연습용 가상 상점입니다.

## 환율과 인터넷 연결

- [Frankfurter v2 API](https://frankfurter.dev/)에서 통화별 KRW 환율을 조회합니다. API 키는 필요하지 않습니다.
- 가격에 환율을 곱하고 1원 단위로 반올림합니다. 소수점 계산은 `Decimal`을 사용합니다.
- 환율 기준일을 표시합니다. 기준 환율은 실시간 카드 결제 환율이 아니며 배송비·세금·관세·카드 수수료는 별도입니다.
- 같은 갱신 작업에서는 통화당 한 번만 환율을 요청합니다. 조회에 실패하면 저장된 환율을 사용하고 **환율 갱신 실패**를 표시합니다. 저장된 환율조차 없으면 가격을 임의로 계산하지 않습니다.
- 인터넷 상태를 30초마다 독립적인 연결 확인 서버 두 곳으로 검사합니다. 둘 다 실패하면 **인터넷 연결 끊김 · 또는 확인 서버에 연결할 수 없어요**를 표시합니다. 방화벽이나 확인 서버 차단도 같은 상태가 될 수 있습니다.
- 개별 판매처 오류는 전체 인터넷 단절로 취급하지 않습니다. 실패한 상품은 마지막으로 확인한 가격과 확인 시각을 유지합니다.
- 연결이 복구되면 다시 조회합니다. 앱 종료 중이거나 컴퓨터가 꺼져 있으면 추적하지 않습니다.
- 기록은 로컬에 저장됩니다. 네트워크 요청 대상은 등록한 판매처, 환율 API, Google/Microsoft 연결 확인 서버입니다. 저금 잔액·입출금 메모는 전송하지 않습니다.

## 데이터와 백업

기본 데이터 파일은 앱 폴더 안의 `data/moa.sqlite3`입니다. 폴더를 삭제하면 기록도 사라질 수 있으니 `설정 · 데이터 백업`에서 백업하세요. 일반 SQLite 파일이며 암호화되어 있지 않습니다.

다른 위치의 데이터 파일을 사용하거나 백업 파일을 바로 열려면:

```powershell
python app.py --data "C:\my-folder\moa-backup.sqlite3"
```

백업 복원은 앱을 닫고 백업 파일을 `data/moa.sqlite3`로 복사하거나, 위처럼 `--data`로 지정하면 됩니다. 현재 앱에서 사용 중인 데이터 파일 자체를 백업 대상으로 선택하는 것은 차단합니다.

자동 조회 간격은 5·15·30·60분 중 선택할 수 있고 이번 실행에만 적용됩니다. 처음 실행하면 30분입니다. 기록 화면은 최근 200개를 보여주며 백업에는 전체 기록이 포함됩니다.

## 미리 보기와 검증

```powershell
python app.py --demo
python -m unittest discover -s tests -v
```

데모의 금액·상품·환율은 **예시**입니다. 네트워크 조회를 하지 않으며 종료하면 데모 변경사항이 사라집니다. 실제 데이터와 섞이지 않습니다.

단축키: `Ctrl+N` 새 저금통, `Ctrl+R` 전체 가격 새로고침, `Esc` 입력창 닫기.

## 소스 구조

```text
moa/
  app.py                Tkinter 화면, 대화상자, 타이머, 비동기 작업
  core.py               SQLite, 가격 추출, HTTP 조회, 환율 계산
  requirements.txt      requests, beautifulsoup4
  tests/test_core.py    금액·가격·환율·오류·백업 테스트
  tests/test_ui.py      실제 입력창 콜백의 통합 테스트
  README.md             실행 및 사용 안내
  VALIDATION.md         검증 결과와 확인 범위
```

가격 추적은 작업 스레드에서 실행하고 화면·DB 변경은 메인 스레드에서 처리합니다. 조회 도중 상품이 수정·삭제되면 이전 조회 결과를 버려 덮어쓰기를 방지합니다. 공개 HTTP(S) 주소만 조회하고, 로컬·사설 네트워크 주소는 거부합니다.

참고 규격: [Schema.org Offer](https://schema.org/Offer), [Frankfurter API](https://frankfurter.dev/), [Python Tkinter](https://docs.python.org/3/library/tkinter.html).
