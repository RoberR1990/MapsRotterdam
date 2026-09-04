"""Ophalen over https, met herkansing.

Het uitgaande verkeer loopt via een proxy die af en toe de TLS-handshake laat
vastlopen: nagemeten met vijf pogingen achter elkaar op dezelfde URL faalde de
eerste na 30 s met een handshake-timeout en waren de vier daarna binnen 0,6 s
klaar. De proxy zelf meldt geen relayfouten, dus het is een hapering en geen
storing -- precies het geval waarvoor een herkansing bestaat.

Zonder dit gaat een ophaalactie bij zo'n hapering verloren. Voor het weer valt
dat mee (Open-Meteo levert de afgelopen week telkens opnieuw), maar de
matrixborden zijn een momentopname: wat er nu boven de weg staat is over een uur
nergens meer te halen. Een gemiste run is daar een gat in de reeks.
"""
import time
import urllib.request

POGINGEN = 3
WACHT_S = 2          # verdubbelt per poging: 2, 4


def haal(url, timeout=60, pogingen=POGINGEN):
    """De inhoud van `url` als bytes. Gooit de laatste fout door als het
    na alle pogingen niet lukt -- stil falen is erger dan luid falen."""
    laatste = None
    for poging in range(pogingen):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as r:
                return r.read()
        except Exception as e:            # netwerk, TLS, HTTP -- alles opnieuw
            laatste = e
            if poging < pogingen - 1:
                time.sleep(WACHT_S * 2 ** poging)
    raise laatste
