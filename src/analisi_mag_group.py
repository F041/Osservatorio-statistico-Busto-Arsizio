import pandas as pd
from pathlib import Path

# Percorso del file CSV processato
data_path = Path(__file__).parent.parent / "data" / "processed_data" / "processed_pagamenti.csv"

# Carica il CSV
try:
    df = pd.read_csv(data_path, encoding="utf-8-sig")
except Exception as e:
    print(f"Errore nel caricamento del file: {e}")
    exit(1)

# Filtra solo le righe di MAGGIOLI S.P.A.
df_mag = df[df["Beneficiario"].str.upper().str.contains("MAGGIOLI S.P.A.")].copy()

# Funzione per assegnare un macrogruppo in base alla descrizione
# (puoi personalizzare le regole qui sotto)
def assegna_macrogruppo(descrizione):
    desc = str(descrizione).lower()
    if "hosting" in desc or "dominio" in desc:
        return "Hosting e Dominio"
    if "manut" in desc or "assistenza" in desc or "supporto" in desc:
        return "Assistenza/Manutenzione Software"
    if "conservaz" in desc:
        return "Conservazione Documenti"
    if "formaz" in desc or "corso" in desc:
        return "Formazione"
    if "modulo" in desc or "software" in desc:
        return "Fornitura Software"
    if "cloud" in desc:
        return "Cloud"
    if "spedizion" in desc or "postali" in desc:
        return "Spese Postali/Spedizioni"
    return "Altro"

# Applica la funzione per creare la colonna Macrogruppo
df_mag["Macrogruppo"] = df_mag["DescrizioneMandato"].apply(assegna_macrogruppo)

# Raggruppa per Anno e Macrogruppo e somma l'importo
risultato = df_mag.groupby(["Anno", "Macrogruppo"], dropna=False)["ImportoEuro"].sum().reset_index()

# Ordina per anno e importo decrescente
risultato = risultato.sort_values(["Anno", "ImportoEuro"], ascending=[True, False])

# Salva il risultato su CSV
output_path = Path(__file__).parent.parent / "data" / "processed_data" / "maggioli_riepilogo_per_macrogruppo.csv"
risultato.to_csv(output_path, index=False, encoding="utf-8-sig")

# Stampa a video
print("Tabella riepilogativa dei costi per MAGGIOLI S.P.A. per anno e macrogruppo:")
print(risultato)
print(f"\nRisultato salvato in: {output_path}")