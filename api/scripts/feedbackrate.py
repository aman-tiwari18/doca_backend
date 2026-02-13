import argparse
import pandas as pd
from transformers import pipeline
from tqdm import tqdm
import os


BATCH_SIZE = 32
DEVICE = -1  # -1 = CPU, 0 = GPU (Change to 0 if GPU available)


parser = argparse.ArgumentParser(description="Rate feedback sentiment")
parser.add_argument("--input", type=str, default="output.xlsx", help="Input Excel file")
parser.add_argument("--output", type=str, default="output_rated.xlsx", help="Output Excel file")
args = parser.parse_args()

INPUT_FILE = args.input
OUTPUT_FILE = args.output


print("Loading model...")
classifier = pipeline(
    "sentiment-analysis",
    model="cardiffnlp/twitter-xlm-roberta-base-sentiment",
    device=DEVICE
)


def map_to_5(label, score):
    label = label.lower()
    if label == "negative":
        if score > 0.7:
            return 1  # Very Poor
        return 2      # Poor
    if label == "positive":
        if score > 0.7:
            return 5  # Excellent
        return 4      # Good
    return 3          # Average


def main():
    if not os.path.exists(INPUT_FILE):
        print(f"Error: Input file '{INPUT_FILE}' not found.")
        return

    print(f"Reading {INPUT_FILE}...")
    try:
        df = pd.read_excel(INPUT_FILE)
    except Exception as e:
        print(f"Error reading Excel file: {e}")
        return

    # Combine text columns
    print("Pre-processing text data...")
    df['text_data'] = df.apply(
        lambda row: ' '.join(filter(None, [
            str(row['Remark']) if pd.notna(row['Remark']) else '', 
            str(row['unUnsatisfactory']) if pd.notna(row['unUnsatisfactory']) else '', 
            str(row['ExperiencewithNCH']) if pd.notna(row['ExperiencewithNCH']) else ''
        ])).strip(),
        axis=1
    )

    texts = df['text_data'].tolist()
    ratings = []
    
    print(f"Processing {len(texts)} entries...")
    
    # Process in batches
    for i in tqdm(range(0, len(texts), BATCH_SIZE)):
        batch_texts = texts[i : i + BATCH_SIZE]
        
        # Handle empty strings which might cause issues with the model
        batch_results = []
        valid_indices = []
        valid_inputs = []

        for idx, text in enumerate(batch_texts):
            if text and len(text) > 5:
                valid_inputs.append(text)
                valid_indices.append(idx)
            else:
                # Default rating for empty/short text
                pass 

        if valid_inputs:
            model_outputs = classifier(
                valid_inputs,
                batch_size=BATCH_SIZE,
                truncation=True,
                max_length=512
            )
            
            # Reconstruct batch results
            current_batch_ratings = [None] * len(batch_texts)
            
            for j, out in enumerate(model_outputs):
                original_idx = valid_indices[j]
                label = out['label']
                score = out['score']
                rating = map_to_5(label, score)
                current_batch_ratings[original_idx] = rating

            ratings.extend(current_batch_ratings)
        else:
            ratings.extend([None] * len(batch_texts))

    df['rating'] = ratings

    print(f"Saving to {OUTPUT_FILE}...")
    df.drop(columns=['text_data'], inplace=True)
    
    df.to_excel(OUTPUT_FILE, index=False)
    print("Done!")

if __name__ == "__main__":
    main()
