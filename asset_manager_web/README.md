# Skyforge Asset Manager Web

Prototype autonome de l'Asset Manager, sans dépendance ni étape de build.

## Lancer

Ouvrir `index.html` dans un navigateur, ou démarrer un petit serveur local:

```powershell
cd asset_manager_web
python -m http.server 8080
```

Puis ouvrir `http://localhost:8080`.

## Video Library

Dans l'onglet `Video Library`:

- `Ouvrir un Board` demande l'acces au dossier racine d'un projet, lit
  `.skyforge_board.json` et charge les videos referencees dans
  `.skyforge_board_assets`.
- `Ajouter un dossier` indexe recursivement les videos d'un dossier libre.
- Un clic selectionne la carte et affiche ses informations dans l'inspecteur.
- Un double-clic ouvre le lecteur video local.
- L'inspecteur affiche une preview arrêtée; son bouton Lire lance la vidéo sur place.
- Les MP4 ComfyUI compatibles exposent leur prompt, facilement copiable, dans l'inspecteur.
- Deux a quatre videos peuvent etre selectionnees pour une comparaison.
- `Telecharger une copie` permet de recuperer le fichier choisi.

Les fichiers restent locaux et ne sont pas envoyes vers un serveur. L'autorisation
de dossier est accordee par le navigateur pour la session courante.

MP4 et WebM sont les formats les plus fiables dans un navigateur. La lecture des
MOV, AVI et MKV depend des codecs disponibles sur la machine.

## Structure

- `index.html`: structure de l'application
- `styles.css`: design responsive
- `app.js`: données de démonstration et interactions

Le prototype simule actuellement les données. Une prochaine intégration peut exposer les modules Python existants (`core.asset_browser`, `core.asset_inventory`, `core.pipeline`) via une API locale.
