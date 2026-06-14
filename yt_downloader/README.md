# 🎬 YouTube Downloader — HD교육컨설팅

유튜브 영상(MP4) 및 음원(MP3)을 다운로드할 수 있는 웹 애플리케이션입니다.

---

## 📋 사전 요구사항

### 1. Python 3.8 이상
```bash
python --version
```

### 2. ffmpeg 설치 (필수 — MP3 변환에 필요)

**Windows:**
1. https://ffmpeg.org/download.html 에서 다운로드
2. 또는 winget 사용:
   ```
   winget install ffmpeg
   ```
3. 또는 Chocolatey 사용:
   ```
   choco install ffmpeg
   ```

**macOS:**
```bash
brew install ffmpeg
```

**Ubuntu/Debian:**
```bash
sudo apt install ffmpeg
```

---

## 🚀 실행 방법

### 1. 의존성 설치
```bash
pip install -r requirements.txt
```

### 2. 서버 실행
```bash
python app.py
```

### 3. 브라우저에서 접속
```
http://localhost:5000
```

---

## 📁 디렉토리 구조
```
yt_downloader/
├── app.py               # Flask 메인 서버
├── requirements.txt     # Python 패키지 목록
├── README.md            # 이 파일
├── templates/
│   └── index.html       # 웹 UI
└── downloads/           # 다운로드 임시 폴더 (자동 생성)
```

---

## ✅ 지원 기능

| 기능           | 설명                                      |
|----------------|-------------------------------------------|
| MP3 다운로드   | 최고/고음질(192k)/보통(128k)/저음질(96k) |
| MP4 다운로드   | 최고화질/1080p/720p/480p/360p            |
| 썸네일 표시    | 영상 미리보기 이미지                      |
| 진행률 표시    | 실시간 다운로드 진행률 + 속도 + 남은 시간|
| 클립보드 감지  | URL 붙여넣기 시 자동 정보 조회            |

## 🔗 지원 URL 형식
- `https://www.youtube.com/watch?v=VIDEO_ID`
- `https://youtu.be/VIDEO_ID`
- `https://www.youtube.com/shorts/VIDEO_ID`
- `https://music.youtube.com/watch?v=VIDEO_ID`

---

## ⚠️ 주의사항

- 저작권이 있는 콘텐츠의 무단 다운로드는 법적 책임이 따를 수 있습니다.
- 개인적인 용도로만 사용하시고, 크리에이터의 저작권을 존중해 주세요.
- 연령 제한 영상은 YouTube 쿠키 로그인 설정이 필요합니다.

---

개발: HD교육컨설팅 | hhd77@hanmail.net
