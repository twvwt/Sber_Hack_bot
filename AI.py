from openai import OpenAI
import json

def AIAssistent():
    client = OpenAI(
        api_key="sk-aitunnel-G7rLaPiWxw6sDX5WPKqhoi58Liy6SCIr",
        base_url="https://api.aitunnel.ru/v1/",
    )
    
    request = '''
    Место: Казань
    🎭 Формат: выезд на природу
    📅 Дата: 12.05.2025
    💰 Бюджет: 100000 ₽
    👥 Гостей: 5
    Это данные, которые мне предоставили родственники, сформируй топ-5 мест, чтобы уложиться в бюджет напиши название(адре).Сформируй JSON файлом.Нужен только массив с названием, адресом и описанием. Дай чисто JSON без лишнего текста'''
    
    try:
        chat_result = client.chat.completions.create(
            messages=[{"role": "user", "content": request}],
            model="deepseek-r1",
            max_tokens=50000,
        )
        
        # Извлекаем содержимое сообщения
        response_content = chat_result.choices[0].message.content
        
        # Пытаемся распарсить JSON из ответа
        try:
            json_data = json.loads(response_content)
            return json_data
        except json.JSONDecodeError:
            # Если не получилось распарсить, возвращаем как есть
            return {"error": "Invalid JSON format", "response": response_content}
            
    except Exception as e:
        return {"error": str(e)}

# Получаем и выводим результат
result = AIAssistent()
print(json.dumps(result, indent=2, ensure_ascii=False))