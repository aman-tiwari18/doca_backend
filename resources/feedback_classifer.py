from utility import connectDB_alchemy
from sqlalchemy.sql import text 

def classify_review(text: str) -> str:
    text = text.lower().strip()

    excellent_keywords = [
    "excellent", "awesome", "amazing", "superb",
    "fantastic", "best", "wonderful", "outstanding",
    "perfect", "brilliant", "5star", "5 star",
    "five star", "5/5", "10 out of 10",
    "fully satisfying", "too good", "mind blowing",
    "very fast service", "bahut accha", "bahut acha",
    "bohot accha", "bohot acha", "kamaal", "kamal",
    "super fast", "impressed a lot", "excellent service"
    ]


    very_good_keywords = [
    "very good", "great", "very nice", "really good",
    "pleased", "very satisfied", "very happy",
    "quick service", "4 star", "4star",
    "accha laga", "acha laga", "bohot accha experience",
    "good experience", "quick response", "quickly done"
   ]

    good_keywords = [
    "good", "nice", "satisfied", "happy",
    "thanks", "thank you", "thanku",
    "resolved", "helpful", "resolution",
    "3star", "3 star",
    "solution", "theek hai", "thik hai",
    "achha", "acha", "okay", "ok", "fine",
    "issue solved", "problem solved"
    ]

    poor_keywords = [
    "average", "not bad", "not happy",
    "poor", "bad", "disappointed", "unsatisfied",
    "unhappy", "could be better", "preshan", "pareshan",
    "itna slow", "slow", "delayed", "delay", "delays",
    "waiting", "waiting time", "2 star", "2star",
    "no action", "nothing", "incomplete",
    "unfair", "unfairly", "partial",
    "no response", "no one", "lack of",
    "lacking", "no resolution", "inadequate",
    "low quality", "not proper", "improvement needed",
    "thoda slow", "thoda problem"
    ]

    very_poor_keywords = [
    "worst", "most worst", "horrible", "terrible",
    "very bad", "awful", "not resolved", "not helpful",
    "never again", "scam", "fraud", "irrelevant",
    "threatening", "abusive", "1 star", "1star",
    "hate", "disgusting", "not working", "not fixed",
    "useless", "unacceptable", "disaster",
    "ripoff", "rip off", "not satisfied", "not happy",
    "not good", "not great", "pathetic",
    "bakwas", "bilkul bekar", "bekar", "kharab",
    "ghatiya", "faltu", "zero star", "0 star",
    "very worst", "worst experience"
    ]



    # ---- PRIORITY ORDER (important) ----
    # very_poor → poor → excellent → very_good → good

    # 1. VERY POOR
    for kw in very_poor_keywords:
        if kw in text:
            return "very_poor"

    # 2. POOR
    for kw in poor_keywords:
        # avoid misclassification: "not bad" must hit poor, not good
        if kw in text:
            return "poor"

    # 3. EXCELLENT
    for kw in excellent_keywords:
        if kw in text:
            return "excellent"

    # 4. VERY GOOD
    for kw in very_good_keywords:
        if kw in text:
            return "very_good"

    # 5. GOOD
    for kw in good_keywords:
        # ensure "not good" doesn't classify as good
        if kw in text and "not " + kw not in text:
            return "good"

    return "unknown"

def convert_into_number(classification: str) -> int:
    mapping = {
        "excellent": 5,
        "very_good": 4,
        "good": 3,
        "poor": 2,
        "very_poor": 1,
        "unknown": 0
    }
    return mapping.get(classification, 0)


DB_GET_ALL_FEEDBACK_QUERY = """
SELECT id, Remark FROM tblfeedback WHERE rating IS NULL OR rating = '' and created_at >= '%s' and created_at < '%s';
"""

def classify_all_feedback(start_date: str, end_date: str):
    # db_config = getConfig('database')
    engine = connectDB_alchemy()

    query = text(DB_GET_ALL_FEEDBACK_QUERY % (start_date, end_date))
    with engine.connect() as connection:
        result = connection.execute(query)
        feedbacks = result.fetchall()

    classified_feedbacks = []
    for feedback in feedbacks:
        feedback_id = feedback[0]
        remark = feedback[1] if feedback[1] else ''
        classification = convert_into_number(classify_review(remark))
        classified_feedbacks.append((feedback_id, classification))

    return classified_feedbacks

if __name__ == "__main__":
    from datetime import datetime, timedelta

    start_date = "2024-10-13 00:00:00"
    end_date = "2025-10-06 00:00:00"

    # we need to run above logic for each day
    current_date = datetime.strptime(start_date, "%Y-%m-%d %H:%M:%S")
    end_datetime = datetime.strptime(end_date, "%Y-%m-%d %H:%M:%S")

    while current_date < end_datetime:
        next_date = current_date + timedelta(days=1)
        results = classify_all_feedback(current_date.strftime("%Y-%m-%d %H:%M:%S"), next_date.strftime("%Y-%m-%d %H:%M:%S"))
        for res in results:
            print(f"Feedback ID: {res[0]}, Classified Rating: {res[1]}")
        
        # insert rating back to tblfeedback
        engine = connectDB_alchemy()
        with engine.connect() as connection:
            for feedback_id, rating in results:
                update_query = text(f"UPDATE tblfeedback SET rating = {rating} WHERE id = {feedback_id};")
                connection.execute(update_query)
                connection.commit()

        current_date = next_date
    print("Classification and update completed.")
    