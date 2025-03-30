document.addEventListener('DOMContentLoaded', function() {
    // Устанавливаем минимальную дату - сегодня
    const today = new Date().toISOString().split('T')[0];
    document.getElementById('deadline').min = today;
    
    // Обработчики событий
    document.querySelector('.sber-button').addEventListener('click', assignTask);
});

async function assignTask() {
    const task = document.getElementById('taskSelect').value;
    const userId = document.getElementById('userSelect').value;
    const deadline = document.getElementById('deadline').value;
    
    if (!task || !userId || !deadline) {
        alert('Заполните все поля');
        return;
    }
    
    try {
        const response = await fetch(`/assign_task/{{ chat_id }}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                task: task,
                user_id: userId,
                deadline: deadline
            })
        });
        
        const result = await response.json();
        
        if (response.ok) {
            location.reload();
        } else {
            alert(result.message || 'Ошибка при назначении задачи');
        }
    } catch (error) {
        console.error('Error:', error);
        alert('Ошибка при назначении задачи');
    }
}

async function completeTask(task) {
    try {
        const response = await fetch(`/complete_task/{{ chat_id }}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                task: task
            })
        });
        
        const result = await response.json();
        
        if (response.ok) {
            location.reload();
        } else {
            alert(result.message || 'Ошибка при завершении задачи');
        }
    } catch (error) {
        console.error('Error:', error);
        alert('Ошибка при завершении задачи');
    }
}

async function deleteTask(task) {
    if (!confirm('Вы уверены, что хотите удалить эту задачу?')) return;
    
    try {
        const response = await fetch(`/delete_task/{{ chat_id }}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                task: task
            })
        });
        
        const result = await response.json();
        
        if (response.ok) {
            location.reload();
        } else {
            alert(result.message || 'Ошибка при удалении задачи');
        }
    } catch (error) {
        console.error('Error:', error);
        alert('Ошибка при удалении задачи')