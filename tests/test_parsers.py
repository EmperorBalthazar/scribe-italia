from app import app, db, Province, City, Report, User, parse_people, parse_groups, parse_armies, parse_sightings


def test_parse_people():
    text = '''| Sator , Cavaliere Piombino | 255PR |
| Balthazar , sì, sono io. | 255PR |
| Ximaena | 30PR |'''
    result = parse_people(text)
    assert result == [
        {'nickname': 'Sator', 'pr': 255},
        {'nickname': 'Balthazar', 'pr': 255},
        {'nickname': 'Ximaena', 'pr': 30},
    ]


def test_parse_groups():
    text = '''Gruppo Armato di Clarissal, Valeryoo
Con l'autorizzazione
Chiedete di unirvi'''
    result = parse_groups(text)
    assert result[0]['leader'] == 'Clarissal'
    assert result[0]['members'] == ['Clarissal', 'Valeryoo']


def test_parse_armies_none():
    assert parse_armies('Nessuno') == []


def test_parse_sightings():
    assert parse_sightings('Oggi per strada avete visto Balthazar') == ['Balthazar']


def test_parse_people_direct_browser_tabs():
    text = "Sator , Cavaliere Piombino\t255PR\t\nBalthazar , sì, sono io.\t255PR\t\nXimaena\t30PR\t"
    assert parse_people(text) == [
        {'nickname': 'Sator', 'pr': 255},
        {'nickname': 'Balthazar', 'pr': 255},
        {'nickname': 'Ximaena', 'pr': 30},
    ]


def test_parse_people_plain_text():
    text = "Sator , Cavaliere Piombino 255PR\nBalthazar , sì, sono io. 255PR\nXimaena 30PR"
    assert parse_people(text) == [
        {'nickname': 'Sator', 'pr': 255},
        {'nickname': 'Balthazar', 'pr': 255},
        {'nickname': 'Ximaena', 'pr': 30},
    ]


def test_parse_enemy_bulk_forum_markdown():
    from app import parse_enemy_bulk
    text = '''1. [*Alaryk Alaryk*](https://forum2.renaissancekingdoms.com/viewtopic.php?p=33106034#) ([image](https://forum2.renaissancekingdoms.com/images/icon_fiche.png))
8. [*Maso_donati Maso_donati*](https://forum2.renaissancekingdoms.com/viewtopic.php?p=33106034#) ([image](https://forum2.renaissancekingdoms.com/images/icon_fiche.png)) già noto come Leonard_da_vinci
11. [*Sinibaldo_donati Sinibaldo_donati*](https://forum2.renaissancekingdoms.com/viewtopic.php?p=33106034#) ([image](https://forum2.renaissancekingdoms.com/images/icon_fiche.png)) già noto come Ezio.donati.
17. [*Kutalmis. Kutalmis.*](https://forum2.renaissancekingdoms.com/viewtopic.php?p=33106034#) ([image](https://forum2.renaissancekingdoms.com/images/icon_fiche.png))'''
    assert parse_enemy_bulk(text) == ['Alaryk', 'Maso_donati', 'Sinibaldo_donati', 'Kutalmis.']


def test_parse_people_stops_nickname_at_first_space():
    text = '''Enak73 d'Ozouf 255PR
Federer de Momignies 255PR
Jamess. de Chambéry 146PR
Melissende_ de Nivellus 133PR
Landry. , Baccard di Leostilla 255PR'''
    assert parse_people(text) == [
        {'nickname': 'Enak73', 'pr': 255},
        {'nickname': 'Federer', 'pr': 255},
        {'nickname': 'Jamess.', 'pr': 146},
        {'nickname': 'Melissende_', 'pr': 133},
        {'nickname': 'Landry.', 'pr': 255},
    ]
