import spacy
import pandas as pd


nlp = spacy.load(
    "en_core_web_lg"
)


df = pd.read_excel(
    "clean_text.xlsx"
)


terms = []


for text in df["clean_text"]:

    doc = nlp(str(text))

    for chunk in doc.noun_chunks:

        terms.append(
            chunk.text
        )



result = pd.DataFrame(
    terms,
    columns=[
        "candidate_term"
    ]
)


result = result.drop_duplicates()


result.to_excel(
    "candidate_glossary.xlsx",
    index=False
)


print("Glossary selesai")