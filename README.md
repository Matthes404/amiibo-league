# Amiibo League

## League Structure

### Ideen 
 - Candidates 
	 - Qualifier etc..

- 1 Champion
	- 4-große Gruppen
                - initialisierung durch schnelles Swiss (4 Runden, nicht Rating spezifisch)
                - Swiss kann im Webinterface unter "Swiss" gestartet und gespielt werden
                - Nach Abschluss der 4 Runden werden automatisch Ligen mit je vier Spielern gebildet (die letzte Liga kann größer sein)
                - Erster steigt auf
                - Letzter steigt ab
                - Nach Abschluss aller Ligaspiele kann per "Finish League" die Saison beendet werden
                        - Sieger jeder Liga steigt auf, Letzter steigt ab
                        - Anschließend pausiert die Liga und jeweils zwei Gruppen werden in ein K.O.-Bracket gesteckt (A+B, C+D, usw.)
                        - Gewinner eines Brackets erhält einen entsprechenden "KoSieg"-Eintrag
                        - Sind alle K.O.-Runden gespielt, startet automatisch die nächste Saison mit den neuen Ligen
		- ca. 91 Teilnehmer -> 91 / 4 = ~22-23
			- Falls nicht teilbar an letzte Gruppe anhängen
			- Jeweils 4 Gruppen bilden nach Saison ein K.O. (ersten 4, die danach usw. + zuerst werden auf und abstiege behandelt)
	- Auf- und Abstieg
	- Ersten Gruppen gehen in K.O. Bracket (bzw. alle in irgendeins, je nach Anzahl Gruppen)
Ziel: Alle Spielen weiterspielen, gleiche / ähnliche Anzahl spiele für Elo auswertung

| Amiibo | Elo | Titel |
|--------|-----|-------|
| Test 1 | 1800 | FM |
| Test 2 | 1950 | IM |
| Test 3 | 2100 | GM |

Die Leaderboard-Ansicht zeigt zusätzlich die gewonnenen "KoSieg"-Titel an.

## Einzelspiel

Spiel ist mit 3 Stocks + 3 Minuten auf Omega-Stage
Bei Zeitablauf gewinnt der mit mehr Kills / Draw möglich
Kills sind Punkte
- 3-0
- 3-1
- 3-2
- 2-2
- etc..


## Zu Elosystem

### Elo initial
Jeder Startet mit 1500
Glicko 2 Elosystem (evtl. erweitert durch größe der Siege)


### Titel
Die Titel orientieren sich am Elo sowie an gewonnenen K.O.-Bracket­uellen.
Es wird immer nur der höchste erreichte Titel angezeigt.

- **FM** – ab 1800 Elo und mindestens **ein** Sieg in einem Bracket
  der Klassen **EF** oder höher (also EF, CD oder AB).
- **IM** – ab 1900 Elo und mindestens **zwei** Siege in Brackets der
  Klassen **CD** oder höher.
- **GM** – ab 2000 Elo und mindestens **drei** Siege im obersten Bracket
  **AB**.

Titel gehen bei Elo-Verlust nicht verloren.
