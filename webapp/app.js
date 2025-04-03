const tg = window.Telegram.WebApp;

tg.expand();
tg.enableClosingConfirmation();

document.getElementById('submit').addEventListener('click', () => {
    const login = document.getElementById('login').value.trim();
    const amount = parseFloat(document.getElementById('amount').value);
    
    if (!login) {
        tg.showAlert('Введите Steam логин!');
        return;
    }
    
    if (!amount || amount <= 0) {
        tg.showAlert('Введите корректную сумму!');
        return;
    }
    
    tg.sendData(JSON.stringify({
        login: login,
        amount: amount
    }));
    
    tg.close();
});