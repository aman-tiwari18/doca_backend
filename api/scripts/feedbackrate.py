import time
import mysql.connector
from transformers import pipeline
from tqdm import tqdm


# ================== CONFIG ================== #

DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "rootpassword123",
    "database": "consumer_db_1",
    "port": 3306
}

BATCH_SIZE = 256        # Increase if GPU (512/1024)
SLEEP_TIME = 0.1        # Reduce DB load


# ================== MODEL ================== #

classifier = pipeline(
    "sentiment-analysis",
    model="cardiffnlp/twitter-xlm-roberta-base-sentiment",
    device=0    # -1 = CPU, 0 = GPU
)


# ================== LABEL MAPPING ================== #

def map_to_5(label, score):

    label = label.lower()

    if label == "negative":
        if score > 0.7:
            return "Very Poor", score
        return "Poor", score

    if label == "positive":
        if score > 0.7:
            return "Excellent", score
        return "Good", score

    return "Average", score


# ================== DB CONNECTION ================== #

def get_connection():
    return mysql.connector.connect(**DB_CONFIG)


# ================== FETCH ================== #

def fetch_batch(cursor):

    query = """
        SELECT id,
               CONCAT_WS(
                   ' ',
                   NULLIF(Remark, ''),
                   NULLIF(unUnsatisfactory, ''),
                   NULLIF(ExperiencewithNCH, '')
               ) AS text_data
        FROM tblfeedback
        WHERE sentiment_done = FALSE
          AND (
                Remark IS NOT NULL
             OR unUnsatisfactory IS NOT NULL
             OR ExperiencewithNCH IS NOT NULL
          )
        LIMIT %s
    """

    cursor.execute(query, (BATCH_SIZE,))
    return cursor.fetchall()



# ================== UPDATE ================== #

def update_batch(cursor, data):

    query = """
        UPDATE tblfeedback
        SET
            sentiment_rating = %s,
            sentiment_done = TRUE
        WHERE id = %s
    """

    cursor.executemany(query, data)


# ================== MAIN ================== #

def main():

    print("Starting Sentiment Batch Processing...")

    conn = get_connection()
    cursor = conn.cursor()

    total = 0

    while True:

        rows = fetch_batch(cursor)

        if not rows:
            break


        ids = []
        texts = []

        for row in rows:
            if row[1] and len(row[1].strip()) > 5:
                ids.append(row[0])
                texts.append(row[1])
            else:
                # Mark empty rows as done
                cursor.execute("""
                    UPDATE tblfeedback
                    SET sentiment_done = TRUE
                    WHERE id = %s
                """, (row[0],))

        if not texts:
            conn.commit()
            continue


        # --------- MODEL INFERENCE (BATCH) --------- #

        results = classifier(
            texts,
            batch_size=32,
            truncation=True,
            max_length=256
        )


        updates = []

        for i, res in enumerate(results):

            label = res["label"]
            score = float(res["score"])

            final_label, final_score = map_to_5(label, score)

            updates.append((
                final_label,
                ids[i]
            ))


        # --------- UPDATE DB --------- #

        update_batch(cursor, updates)

        conn.commit()


        total += len(updates)

        print(f"Processed: {total}")

        time.sleep(SLEEP_TIME)


    cursor.close()
    conn.close()

    print("Completed. Total processed:", total)



if __name__ == "__main__":
    main()
