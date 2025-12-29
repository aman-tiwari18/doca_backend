from fastapi import APIRouter
from torch import nn
import torch
from transformers import BertTokenizer, BertModel
from pathlib import Path
import sys

# ---------------------------- Path Management ----------------------------
resources_dir = Path(__file__).resolve().parents[2] / "resources"
sys.path.append(str(resources_dir))
# ---------------------------- Import External Utilities ----------------------------
from utility import load_config

# ---------------------------- Import Internal Utilities ----------------------------
config = load_config()


router = APIRouter(
    tags=["Priority Check"]
)


MAX_LENGTH = 128
BERT_MODEL_NAME = config['BERT_MODEL_NAME']
BERT_MODEL_PATH = config['BERT_MODEL_PATH']
PRIORITY_MODEL_PATH = config['PRIORITY_MODEL_PATH']


device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
tokenizer = BertTokenizer.from_pretrained(BERT_MODEL_PATH)


class BERTClassifier(nn.Module):
    def __init__(self, BERT_MODEL_NAME, num_classes):
        super(BERTClassifier, self).__init__()
        self.bert = BertModel.from_pretrained(BERT_MODEL_NAME)
        self.dropout = nn.Dropout(0.1)
        self.fc = nn.Linear(self.bert.config.hidden_size, num_classes)

    def forward(self, input_ids, attention_mask):
        outputs = self.bert(input_ids=input_ids, attention_mask=attention_mask)
        pooled_output = outputs.pooler_output
        x = self.dropout(pooled_output)
        logits = self.fc(x)
        return logits


def predict_sentiment(text, model, tokenizer, device, MAX_LENGTH=128):
    model.eval()
    encoding = tokenizer(text, return_tensors='pt', MAX_LENGTH=MAX_LENGTH, padding='max_length', truncation=True)
    input_ids = encoding['input_ids'].to(device)
    attention_mask = encoding['attention_mask'].to(device)

    with torch.no_grad():
        outputs = model(input_ids=input_ids, attention_mask=attention_mask)
        _, preds = torch.max(outputs, dim=1)
        return preds.item()
        # return 1 if preds.item() == 1 else 0


@router.get("/check_priority/")
def check_urgent(doc):

    priority_model = BERTClassifier(BERT_MODEL_PATH, 2).to(device)
    priority_model.load_state_dict(torch.load(PRIORITY_MODEL_PATH))
    priority_model.eval()
    sentiment = predict_sentiment(doc, priority_model, tokenizer, device)
    return sentiment