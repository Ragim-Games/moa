# v1.0.0 검증 기록

- 날짜: 2026-11-09 (한국 시간)
- 빌드: Windows 11 x64, Python 3.15.0, PyInstaller 6.22.3, 별도 가상환경
- 형태: 콘솔 창 없는 Windows x64 단일 EXE
- 테스트: `python -m unittest discover -s tests -v` 33개 통과
- EXE: 실제 창 실행 및 한글·저금통 초기 화면 표시 확인
- 패키지 데이터 경로: 임시 압축 해제 위치 대신 `%LOCALAPPDATA%\Moa\moa.sqlite3` 사용. 실행 중 해당 경로에 DB 생성 확인
- 기존 테스트: 입출금, 잔액 수정, 가격 파싱, 환율 계산·실패 처리, 백업 재열기, 상품 수정 중 조회 경쟁 처리, 실제 Tk 대화상자 콜백
- 추가 테스트: 소스 실행 경로 유지, Windows 패키지의 영구 데이터 경로, LOCALAPPDATA 미설정 시 사용자 폴더 대체 경로

소스 버전에서 공개 상품 페이지의 GBP 가격 추출 및 Frankfurter 원화 환산을 실제 네트워크로 확인했습니다. EXE 초기 실행은 네트워크가 제한된 검증 환경이므로 연결 실패 안내가 표시되는 것도 확인했습니다. EXE에서 모든 판매처의 호환성, 모든 Windows 버전 및 macOS/Linux 실행을 검증한 것은 아닙니다. 디지털 서명은 포함하지 않습니다.

빌드 명령:

```powershell
python -m pip install -r requirements-build.txt
python -m PyInstaller --clean --onefile --windowed --noupx --name Moa-v1.0.0-windows-x64 app.py
```

배포물에는 개인 저금 기록, 데이터베이스, 로그인 정보, 가상환경을 포함하지 않습니다.
