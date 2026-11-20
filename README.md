# EditSphere — livres du domaine public prêts pour KDP (broché)

`clean_kdp.py` prend des livres HTML du domaine public (exports Word, pages
ebooksgratuits.com, archives MHTML « Enregistrer la page » de Chrome), les
nettoie et produit pour chacun **un PDF intérieur prêt à téléverser sur Amazon
KDP** pour une impression brochée.

## Ce que fait l'outil

**Nettoyage du texte**
- retire la page de titre du site source, l'ancienne table des matières, la page
  « À propos de cette édition électronique », les mentions et adresses du site,
  les portraits de couverture et tout le balisage Word/web ;
- conserve **tout le texte de l'œuvre** : un contrôle compare mot à mot le texte
  final à la source et signale le moindre écart dans le rapport ;
- notes : les notes de l'auteur passent en **notes de bas de page** ; les notes
  ajoutées par un correcteur ou par un éditeur moderne sont retirées (les
  annotations de Guy Rosa dans *Les Misérables* sont protégées par le droit
  d'auteur : elles sont retirées automatiquement) ;
- typographie française : espaces insécables avant `; : ! ? »` et après `«` ;
- repère les **vers** (poésie, théâtre en vers) et les compose ligne à ligne, sans
  justification ;
- remplace par du texte les mots que la source avait mis en image (mots grecs de
  *Notre-Dame de Paris*) et garde les vraies figures (dessins de *Le Rhin*,
  fac-similés).

**Mise en page KDP**
- format exact au choix (6 × 9 po par défaut ; 5 × 8, 5,25 × 8, 5,5 × 8,5…),
  sans fond perdu ;
- **petit fond calculé selon le nombre de pages**, au-dessus du minimum KDP
  (le PDF est recomposé si nécessaire) ;
- police EB Garamond (licence libre OFL, usage commercial autorisé), incorporée ;
- page de titre, verso avec mentions, ouverture des parties en page impaire,
  titres courants (titre du livre à gauche, chapitre à droite), folios, pages
  blanches vraiment blanches, césure française, veuves et orphelines évitées ;
- **table des matières avec les vrais numéros de page** (à la fin, à la
  française, ou au début).

## Installation

Python 3.10 ou plus récent, puis :

```bash
pip install -r requirements.txt
```

WeasyPrint (le moteur PDF) a besoin de la bibliothèque Pango :

- **macOS** : `brew install pango`
- **Ubuntu / Debian** : `sudo apt install libpango-1.0-0 libpangoft2-1.0-0`
- **Windows** : suivez https://doc.courtbouillon.org/weasyprint/stable/first_steps.html
  (ou utilisez la méthode « sans installation » ci-dessous).

## Utilisation

Tous les livres du dossier `victor-hugo/` (environ 1 à 2 minutes) :

```bash
python3 clean_kdp.py
```

Un seul livre, dans un autre format :

```bash
python3 clean_kdp.py "victor-hugo/CLAUDE GUEUX.html" --format 5.5x8.5
```

Avec votre nom d'éditeur et votre ISBN au verso de la page de titre :

```bash
python3 clean_kdp.py "victor-hugo/quatrevingt-treize.html" --editeur "Éditions Exemple" --isbn "979-10-00000-00-0"
```

Options utiles :

| Option | Effet |
|---|---|
| `--format 6x9` | format KDP en pouces (`5x8`, `5.25x8`, `5.5x8.5`, `6x9`, `6.14x9.21`, `7x10`…) |
| `--taille-police 11` | corps du texte en points (10,5 ou 10 réduit le nombre de pages) |
| `--notes auto\|garder\|retirer` | gestion des notes (défaut `auto`, voir plus haut) |
| `--sommaire fin\|debut\|aucune` | position de la table des matières |
| `--no-parties-page-impaire` | ne pas forcer les parties à commencer en page de droite |
| `--sans-pdf` | nettoyage seul (rapide), pour relire le HTML |
| `--dossier-source`, `--dossier-sortie` | autres dossiers que `victor-hugo/` et `sortie/` |

## Résultat

Pour chaque livre, `sortie/<nom-du-livre>/` contient :

- `<nom>_interieur_6x9.pdf` : **le fichier à téléverser sur KDP** (« Manuscrit ») ;
- `<nom>.html` : le texte nettoyé et mis en page, pour relecture ;
- `rapport.txt` : nombre de pages, marges, contrôle des mots, notes conservées ou
  retirées, éléments supprimés et points **À VÉRIFIER**.

Les fichiers d'origine ne sont jamais modifiés.

## Sans rien installer : GitHub Actions

Dans l'onglet **Actions** du dépôt, choisissez **Intérieurs KDP** puis
**Run workflow** (format, fichier précis ou tous les livres). À la fin, les PDF
et rapports sont téléchargeables dans la section **Artifacts** de l'exécution.

## Ajouter un livre

Déposez le fichier dans `victor-hugo/` (ou un autre dossier avec
`--dossier-source`). Sont reconnus : HTML exporté de Word, pages HTML
d'ebooksgratuits.com, archives `.mhtml` / « Saved by Blink », et les HTML déjà
passés par EditSphere. Lisez ensuite `rapport.txt` :

- **image de contenu introuvable** : placez l'image dans `victor-hugo/images/`,
  ou, si c'est un mot mis en image, ajoutez son texte dans
  `victor-hugo/remplacements.json` (`"nom_image.jpg": "texte"`) ;
- **images en basse résolution** : elles s'impriment mais un peu floues (KDP
  recommande 300 dpi) ; remplacez-les par une meilleure numérisation si vous en
  avez une, même nom de fichier dans `victor-hugo/images/` ;
- **écart de texte** : l'outil s'arrête sur le premier mot différent ; ouvrez le
  HTML pour vérifier.

## Avant de publier sur KDP

- La **couverture** n'est pas produite ici : utilisez le nombre de pages du
  rapport dans le calculateur de couverture de KDP.
- Vérifiez toujours le PDF dans l'**aperçu en ligne** de KDP.
- KDP applique une politique particulière aux **œuvres du domaine public**
  (rubrique d'aide « Public domain content ») : lisez-la avant de publier, en
  particulier si le même texte est déjà largement disponible.

## Tests

```bash
pip install -r requirements-dev.txt
python3 -m pytest -q
```

`index.html` est l'ancien éditeur dans le navigateur (aperçu rapide, sans PDF ni
contrôle du texte) ; pour l'impression, utilisez `clean_kdp.py`.
