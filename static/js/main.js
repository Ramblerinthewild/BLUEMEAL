function highlightCurrentMeal(mealId) {
    const meals = document.querySelectorAll('.meal-card');
    meals.forEach(m => m.style.border = 'none');
    const current = document.getElementById(mealId);
    if (current) {
        current.style.border = '2px solid #1a73e8';
    }
}
