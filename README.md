# Инструкция по запуску ИИ-Штурмана Т-Инвестиций

### 1. Требования к окружению
* Python 3.11+
* Запущенная локально Ollama с моделью Qwen2.5:3b (`ollama run qwen2.5:3b`)

### 2. Установка зависимостей
Проект использует нативные rest-шлюзы и стабильные сборки. Установка одной строкой:
```bash
pip install streamlit langchain-ollama langchain-core pandas numpy pydantic cryptography==41.0.7 --only-binary=:all:
```

### 3. Запуск платформы
Запустите команду в директории проекта:
```bash
python3.11 -m streamlit run app.py
```
Интерфейс автопилота автоматически откроется в браузере по адресу `http://localhost:8501`.

