SOURCE_CREDIBILITY = {
    "BBC_Arabic": 0.93, "CNN_Arabic": 0.88, "France24_Arabic": 0.90,
    "DW_Arabic": 0.88, "AlJazeera_Main": 0.88, "AlArabiya_Latest": 0.85,
    "SkyNews_Latest": 0.85, "Asharq_Latest": 0.83, "RT_Arabic_Main": 0.65,
    "AlMasry_Latest": 0.78, "Ahram_Latest": 0.80, "Youm7_Politics": 0.72,
    "Dostor_News": 0.55, "Veto_Gate": 0.50, "Sada_ElBalad": 0.55,
}

DEFAULT_CREDIBILITY = 0.4

def get_credibility(source_key):
    return SOURCE_CREDIBILITY.get(source_key, DEFAULT_CREDIBILITY)
