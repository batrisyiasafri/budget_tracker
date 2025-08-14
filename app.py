from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from sqlalchemy import func
from sqlalchemy import extract

app = Flask(__name__)
app.secret_key = 'secret-me'

# config for SQLite
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///budget.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# initialise the db
db = SQLAlchemy(app)

# models
class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    type = db.Column(db.String(10), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    description = db.Column(db.String(200), nullable=True)

class BudgetGoal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    category = db.Column(db.String(50), nullable=False)
    month = db.Column(db.String(7), nullable=False)
    amount = db.Column(db.Float, nullable=False)

# routes

# budget goals
@app.route('/budget-goals', methods=['GET', 'POST'])
def budget_goals():
    if request.method == 'POST':
        category = request.form.get('category') or None
        raw_month = request.form.get('month') 

        try:
            parsed_month = datetime.strptime(raw_month, '%m/%Y')
            month = parsed_month.strftime('%Y-%m')
        except ValueError:
            flash('Invalid month format. Please use m/yyyy (e.g., 8/2025).', 'error')
            return redirect(url_for('budget_goals'))

        amount = float(request.form.get('amount'))

        goal = BudgetGoal.query.filter_by(category=category, month=month).first()
        if goal:
            goal.amount = amount
        else:
            goal = BudgetGoal(category=category, month=month, amount=amount)
            db.session.add(goal)

        db.session.commit()
        flash('Budget goal saved!', 'success')
        return redirect(url_for('budget_goals'))

    now = datetime.utcnow()
    current_month = now.strftime('%Y-%m')
    formatted_month = now.strftime('%m/%Y').lstrip("0")

    goals = BudgetGoal.query.filter_by(month=current_month).all()

    return render_template(
        'budget_goals.html',
        goals=goals,
        current_month=current_month,
        formatted_month=formatted_month,
        datetime=datetime
    )

# edit goals
@app.route('/budget-goals/edit/<int:goal_id>', methods=['GET', 'POST'])
def edit_goal(goal_id):
    goal = BudgetGoal.query.get_or_404(goal_id)
    
    if request.method == 'POST':
        category = request.form.get('category') or None
        raw_month = request.form.get('month')

        try:
            parsed_month = datetime.strptime(raw_month, '%m/%Y')
            goal.month = parsed_month.strftime('%Y-%m')
        except ValueError:
            flash('Invalid month format. Please use m/yyyy (e.g., 8/2025).', 'error')
            return redirect(url_for('edit_goal', goal_id=goal_id))

        goal.category = category
        goal.amount = float(request.form.get('amount'))

        db.session.commit()
        flash('Budget goal updated!', 'success')
        return redirect(url_for('budget_goals'))

    formatted_month = datetime.strptime(goal.month, '%Y-%m').strftime('%m/%Y').lstrip("0")
    return render_template('edit_goal.html', goal=goal, formatted_month=formatted_month)

# delete goal
@app.route('/budget-goals/delete/<int:goal_id>', methods=['GET', 'POST'])
def delete_goal(goal_id):
    goal = BudgetGoal.query.get_or_404(goal_id)
    db.session.delete(goal)
    db.session.commit()
    flash('Budget goal deleted!', 'danger')
    return redirect(url_for('budget_goals'))


# display income, expense, and balance summary 
@app.route('/')
def index():
    transactions = Transaction.query.order_by(Transaction.date.desc()).all()

    # calculate income and expense totals
    income_total = db.session.query(func.sum(Transaction.amount)).filter_by(type='income').scalar() or 0
    expense_total = db.session.query(func.sum(Transaction.amount)).filter_by(type='expense').scalar() or 0
    balance = income_total - expense_total

    return render_template(
        'index.html',
        transactions=transactions,
        income_total=income_total,
        expense_total=expense_total,
        balance=balance
    )

# add transaction
@app.route('/add', methods=['POST'])
def add_transaction():
    if request.method == 'POST':
        date_str = request.form['date']
        trans_type = request.form['type']
        category = request.form['category']
        amount = float(request.form['amount'])
        description = request.form['description']

        # parse the date and extract the month
        date = datetime.strptime(date_str, '%Y-%m-%d')
        month_str = date.strftime('%Y-%m')

        # create new transaction
        new_transaction = Transaction(
            date=date,
            type=trans_type,
            category=category,
            amount=amount,
            description=description
        )

        db.session.add(new_transaction)
        db.session.commit()

        # budget check only for expenses
        if trans_type == 'expense':
            # total expense for category this month
            category_expense = db.session.query(func.sum(Transaction.amount)).filter(
                Transaction.type == 'expense',
                Transaction.category == category,
                extract('year', Transaction.date) == date.year,
                extract('month', Transaction.date) == date.month
            ).scalar() or 0

            # check category goal
            category_goal = BudgetGoal.query.filter_by(category=category, month=month_str).first()
            if category_goal and category_expense > category_goal.amount:
                flash(f'You exceeded the budget for category "{category}" (Limit: BND {category_goal.amount})', 'error')

            # total expense overall this month
            total_expense = db.session.query(func.sum(Transaction.amount)).filter(
                Transaction.type == 'expense',
                extract('year', Transaction.date) == date.year,
                extract('month', Transaction.date) == date.month
            ).scalar() or 0

            # check overall goal
            overall_goal = BudgetGoal.query.filter_by(category=None, month=month_str).first()
            if overall_goal and total_expense > overall_goal.amount:
                flash(f'You exceeded your overall monthly budget (Limit: BND {overall_goal.amount})', 'error')

        flash('Transaction added!', 'success')
        return redirect(url_for('index'))


# edit transaction
@app.route('/edit/<int:transaction_id>', methods=['GET', 'POST'])
def edit_transaction(transaction_id):
    transaction = Transaction.query.get_or_404(transaction_id)

    if request.method == 'POST':
        date_str = request.form['date']
        transaction.date = datetime.strptime(date_str, '%Y-%m-%d')
        transaction.type = request.form['type']
        transaction.category = request.form['category']
        transaction.amount = float(request.form['amount'])
        transaction.description = request.form['description']

        db.session.commit()
        flash('Transaction updated!', 'success')
        return redirect(url_for('index'))


    return render_template('edit.html', transaction=transaction)

# delete transaction
@app.route('/delete/<int:transaction_id>')
def delete_transaction(transaction_id):
    transaction = Transaction.query.get_or_404(transaction_id)
    db.session.delete(transaction)
    db.session.commit()
    flash('Transaction deleted!', 'danger')
    return redirect(url_for('index'))


# entry point
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        print("Database created")
    app.run(debug=True)
