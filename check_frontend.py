"""
Проверка, что в main.js есть строка с передачей pair_id
"""

with open('frontend/static/main.js', 'r', encoding='utf-8') as f:
    content = f.read()
    
# Ищем строку с pair_id
if 'pair_id: row.dataset.id' in content:
    print("✅ main.js содержит передачу pair_id")
    
    # Находим и показываем контекст
    for i, line in enumerate(content.split('\n'), 1):
        if 'pair_id:' in line:
            print(f"\nСтрока {i}: {line.strip()}")
else:
    print("❌ main.js НЕ содержит передачу pair_id!")
    print("Нужно обновить файл frontend/static/main.js")

# Проверим также строку с action:'send_pair_order'
lines = content.split('\n')
for i, line in enumerate(lines):
    if "action:'send_pair_order'" in line or 'action:"send_pair_order"' in line:
        print(f"\nНайден payload с send_pair_order на строке {i+1}:")
        # Показываем 15 строк после (весь payload)
        for j in range(i, min(i+15, len(lines))):
            print(f"  {j+1}: {lines[j]}")
        break
