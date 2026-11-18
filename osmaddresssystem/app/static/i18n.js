/* Local UI translations. Only authored labels are translated, never inserted map data. */
'use strict';
window.I18n = (() => {
  const fr = {
    'Road geometry':'G\u00e9om\u00e9trie des routes','Street attributes':'Attributs des routes','Names':'Noms','Buildings':'B\u00e2timents',
    'Not started':'Non commenc\u00e9','Waiting for community':'En attente de la communaut\u00e9','Complete':'Termin\u00e9','Needs correction':'\u00c0 corriger','Verified':'V\u00e9rifi\u00e9',
    'Show areas':'Afficher les zones','Build areas from quartier CSV':'Cr\u00e9er les zones \u00e0 partir du CSV des quartiers',
    'Recorded spellings':'Orthographes enregistr\u00e9es','Provisional':'Provisoire','Preview quartiers':'Pr\u00e9visualiser les quartiers',
    'Neighbouring quartier':'Quartier voisin','Adjust this shared border':'Corriger cette limite commune','Adjust a quartier border':'Corriger une limite de quartier',
    'Save corrected border':'Enregistrer la limite corrig\u00e9e','Field evidence and reason for this correction':'Preuve de terrain et raison de cette correction',
    'Quartiers':'Quartiers','Work areas':'Zones de travail','Whole map':'Carte enti\u00e8re',
    'Choose a quartier':'Choisir un quartier','Choose a work area':'Choisir une zone de travail',
    'Show quartier boundaries':'Afficher les limites des quartiers','Choose...':'Choisir...',
    'Country':'Pays','Project':'Projet','Quartier':'Quartier','Quartier trigram':'Trigramme du quartier','Recorded quartier':'Quartier relevé',
    'Survey record type':'Type de relevé','Legacy record — type not recorded':'Ancien relevé — type non renseigné','Use':'Usage',
    'Place name':'Nom du lieu','Service':'Service','Residents':'Habitants','Generated address':'Adresse générée','Address ID':'Identifiant de l’adresse',
    '{0} road edits could not be applied (edit {1}). Undo the last edit and check the map.':'{0} modifications de routes n’ont pas pu être appliquées (modification {1}). Annulez la dernière modification et vérifiez la carte.',
    'partly: choose to set all of it':'en partie : choisir pour tout régler',
    'gives addresses':'donne des adresses','Small path: its houses take the number where it leaves the street, with a letter (230A, 230B). Compute the addresses to apply.':'Petit chemin : ses maisons prennent le numéro de l’endroit où il quitte la rue, avec une lettre (230A, 230B). Calculez les adresses pour appliquer.',
    ' (where its path leaves the street)':' (là où son chemin quitte la rue)','reached by':'accès par','register':'registre','code':'code','To review':'À revoir',
    'Approve this address':'Valider cette adresse','Correct: use the new address':'Corriger : prendre la nouvelle adresse','Plaque':'Plaque','Draft plaque':'Plaque (brouillon)',
    'Retire (house gone)':'Retirer (maison disparue)','Register: approved addresses are frozen':'Registre : les adresses validées sont figées',
    'Search':'Rechercher','Go to: lat, lon':'Aller à : lat, lon','Paste coordinates such as 5.33195, 10.22380 and press Enter':'Collez des coordonnées comme 5.33195, 10.22380 puis appuyez sur Entrée','Write two numbers: latitude, longitude':'Écrivez deux nombres : latitude, longitude','no plate yet':'pas encore de plaque','no plate: quartier unknown':'pas de plaque : quartier inconnu','Address, family name or survey id (e.g. TCK 0575, HIE-I022)':'Adresse, nom de famille ou identifiant du recensement (ex. TCK 0575, HIE-I022)',
    'Nothing found.':'Rien trouvé.','as in the survey':'comme dans le recensement','Correct the quartier':'Corriger le quartier','Survey wrote:':'Le recensement indique :',
    'Quartier set to {0}. Compute the addresses to apply.':'Quartier changé en {0}. Calculez les adresses pour appliquer.',
    'Quartier back to the survey. Compute the addresses to apply.':'Quartier remis comme dans le recensement. Calculez les adresses pour appliquer.',
    'For the plaque and the address card':'Pour la plaque et la carte d’adresse','quartier':'quartier','name on the plaque':'nom sur la plaque',
    'missing (no family name in the survey)':'manquant (pas de nom de famille dans le recensement)','address':'adresse','incomplete (quartier without trigram)':'incomplète (quartier sans trigramme)',
    'street part':'partie rue','house part':'partie maison','written address':'adresse écrite','survey address id':'identifiant du recensement',
    'contact (private)':'contact (privé)','phone (private)':'téléphone (privé)','persons':'personnes','No survey record imported for this building.':'Aucune fiche du recensement importée pour ce bâtiment.',
    'internal id':'identifiant interne','draft (not validated)':'brouillon (non validée)','retired':'retirée','number':'numéro','side':'côté','status':'statut','use':'usage','residents':'habitants','road point':'point de route',
    'chosen by hand':'choisi à la main','nearest road (purple)':'route la plus proche (violet)','azimuth':'azimut',
    'Change to validate':'Changement à valider','Validate this address':'Valider cette adresse','Validate the change':'Valider le changement',
    'Address card':'Carte d’adresse','Draft address card':'Carte d’adresse (brouillon)',
    'Register: validated addresses and their changes':'Registre : adresses validées et leurs changements',
    'A validated address is the one on the plaque. When a road edit would change it, the change waits here; once validated, the family is on the list to inform (before / after, name, phone, position).':'Une adresse validée est celle de la plaque. Si une modification de route la changerait, le changement attend ici ; une fois validé, la famille est sur la liste à prévenir (avant / après, nom, téléphone, position).',
    'Choose a work area to validate its addresses together.':'Choisissez une zone de travail pour valider ses adresses ensemble.','Families to inform (CSV)':'Familles à prévenir (CSV)',
    'Address validated: it changes only when you validate a change.':'Adresse validée : elle ne change que si vous validez un changement.','Not validated: the address is not complete.':'Non validée : l’adresse n’est pas complète.',
    'Validate every complete address in {0}?':'Valider toutes les adresses complètes de {0} ?','{0} validated, {1} already validated, {2} not complete.':'{0} validées, {1} déjà validées, {2} incomplètes.',
    'Why does the address change? (kept in its history and in the list of families to inform)':'Pourquoi l’adresse change-t-elle ? (gardé dans son historique et dans la liste des familles à prévenir)',
    'Change validated. The family is on the list to inform.':'Changement validé. La famille est sur la liste à prévenir.',
    'Why do these addresses change? (kept in their history and in the list of families to inform)':'Pourquoi ces adresses changent-elles ? (gardé dans leur historique et dans la liste des familles à prévenir)',
    '{0} changes validated. Download the list of families to inform.':'{0} changements validés. Téléchargez la liste des familles à prévenir.',
    'Approving freezes an address: later road edits never change it; the houses they would change are listed for review. Only complete addresses (street named, road found) can be approved.':'Valider fige une adresse : les modifications de routes ne la changent plus ; les maisons qu’elles changeraient sont listées pour vérification. Seules les adresses complètes (rue nommée, route trouvée) peuvent être validées.',
    'Choose a work area to approve its addresses together.':'Choisissez une zone de travail pour valider ses adresses ensemble.','Download the register (CSV)':'Télécharger le registre (CSV)',
    'Address approved: it will not change any more.':'Adresse validée : elle ne changera plus.','Not approved: the address is not complete.':'Non validée : l’adresse n’est pas complète.',
    'Approve every complete address in {0}? They will not change any more.':'Valider toutes les adresses complètes de {0} ? Elles ne changeront plus.',
    '{0} approved, {1} already approved, {2} not complete.':'{0} validées, {1} déjà validées, {2} incomplètes.',
    'Why is the approved address corrected? (kept in its history)':'Pourquoi corriger l’adresse validée ? (gardé dans son historique)','Address corrected; its code stays the same.':'Adresse corrigée ; son code reste le même.',
    'Why is this address retired? (e.g. house demolished)':'Pourquoi retirer cette adresse ? (ex. maison démolie)','Address retired. Its number and code will never be given again.':'Adresse retirée. Son numéro et son code ne seront jamais redonnés.','Road check':'Vérification des routes','Edits not applied':'Modifications non appliquées','Gaps: an end stops close to a road':'Écarts : une extrémité s’arrête près d’une route',
    'Roads on top of each other':'Routes superposées','Roads cross without a junction':'Routes qui se croisent sans carrefour','Not connected to the network':'Non reliées au réseau',
    'Very short sections':'Tronçons très courts','Drawn road ends not connected':'Extrémités de routes tracées non reliées','Drivable not set':'Carrossable non renseigné',
    'deleted portion':'portion supprimée','connection':'connexion','reshape':'correction de tracé','the whole map':'toute la carte','Checking the roads...':'Vérification des routes...',
    '{0} m gap':'écart de {0} m','{0} · edit {1}':'{0} · modification {1}','street {0} · {1} m':'rue {0} · {1} m','{0} m':'{0} m','at {0}, {1}':'à {0}, {1}',
    '{0} problems left in {1}.':'{0} points à vérifier dans {1}.','Nothing left to check in {0}.':'Plus rien à vérifier dans {0}.','Click one to zoom to it.':'Cliquez sur un point pour zoomer.',
    'Lists what to look at in {0}: gaps, roads on top of each other, very short sections, unconnected ends, edits that do not apply. Nothing is changed by the check.':'Liste ce qu’il faut regarder dans {0} : écarts, routes superposées, tronçons très courts, extrémités non reliées, modifications non appliquées. La vérification ne change rien.',
    'Check {0}':'Vérifier {0}','Check again':'Vérifier à nouveau','OK as is':'Correct tel quel','List again':'Remettre dans la liste','show the {0} marked OK':'afficher les {0} marqués corrects','Hide':'Masquer',
    'Coordinates':'Coordonnées','Internal record ID':'Identifiant interne',
    'Community mapping':'Cartographie communautaire','Community map':'Carte communautaire',
    'Your workspace':'Votre espace de travail','Map guide':'Guide de la carte',
    'Existing roads':'Routes existantes','Added roads':'Routes ajoutées','Connection to review':'Connexion à vérifier',
    'Colours vary in the Street types and IDs and Street names tabs.':'Les couleurs changent dans les onglets Types et identifiants des rues et Noms des rues.',
    'Right-click a road for editing tools. Select a work area to review the map one section at a time.':'Faites un clic droit sur une route pour la modifier. Choisissez une zone de travail pour vérifier la carte portion par portion.',
    'Edit streets':'Modifier les routes','Street IDs':'Identifiants','Street types and IDs':'Types et identifiants des rues','Street ids':'Identifiants des rues','Street names':'Noms des rues','Addresses':'Adresses',
    '1 · Edit streets':'1 · Routes','2 · Street IDs':'2 · Identifiants','2 · Street types and IDs':'2 · Types et identifiants','3 · Street names':'3 · Noms des rues','4 · Addresses':'4 · Adresses',
    '↶ Undo':'↶ Annuler','↷ Redo':'↷ Rétablir','💾 Save checkpoint':'💾 Enregistrer une étape','🕓 Checkpoints':'🕓 Étapes enregistrées','⬇ Export':'⬇ Exporter',
    'Undo':'Annuler','Redo':'Rétablir','Save checkpoint':'Enregistrer une étape','Checkpoints':'Étapes enregistrées','Export':'Exporter','Warnings':'Alertes',
    'Undo the last edit':'Annuler la dernière modification','Go back to an older saved checkpoint':'Revenir à une étape enregistrée',
    'Edits are saved at once. Save makes a named checkpoint (with the street ids) you can come back to':'Les modifications sont enregistrées immédiatement. Une étape nommée permet de revenir à cet état.',
    'Active warnings':'Points à vérifier','Show or hide the list':'Afficher ou masquer la liste','No warnings.':'Aucune alerte.',
    'Reference point':'Point de référence','where the numbering starts':'origine de la numérotation','Streets':'Rues','one row per street id':'une ligne par identifiant',
    'Edges':'Tronçons','one row per edge':'une ligne par tronçon','Nodes':'Nœuds','Buildings + addresses':'Bâtiments et adresses','Street signs':'Plaques de rue',
    'Changes for OpenStreetMap':'Modifications pour OpenStreetMap','new + modified streets':'rues ajoutées et modifiées','Street names given':'Noms attribués',
    'Work areas':'Zones de travail','Whole map':'Carte entière','Progress':'Avancement','Save area progress':'Enregistrer l’avancement',
    'Not reviewed':'Non vérifiée','In progress':'En cours','Reviewed':'Vérifiée','Needs review':'À vérifier',
    'not reviewed':'non vérifiée','in progress':'en cours','reviewed':'vérifiée','needs review':'à vérifier',
    'Show grid':'Afficher le quadrillage','Cell size':'Taille des cases','Automatic':'Automatique','Create work areas':'Créer les zones',
    "Divide this project's area into a review grid.":'Divisez le territoire en zones à vérifier.',
    'What was checked? What is uncertain?':'Qu’avez-vous vérifié ? Que reste-t-il à éclaircir ?',
    'Focus highlights an area and narrows road selection. Roads crossing its boundary stay whole. Progress is your review record, not automatic verification.':'La sélection met une zone en évidence. Les routes qui la traversent restent entières. L’avancement indique votre vérification manuelle.',
    'Area progress saved':'Avancement enregistré','Road editing':'Modifier une route','Road section':'Tronçon de route',
    'Reshape this section':'Ajuster ce tronçon','Delete a portion (two points)':'Supprimer une portion (deux points)',
    'Delete this whole section':'Supprimer ce tronçon entier','Connect an endpoint to a road':'Raccorder une extrémité à une route',
    'Draw a road from two points':'Dessiner une route entre deux points','Extend from a free endpoint':'Prolonger une extrémité libre','Street IDs / group segments':'Identifiants / regrouper des tronçons',
    'free end':'extrémité libre','junction':'carrefour','Choose this free endpoint':'Choisir cette extrémité libre','Already a junction':'Déjà un carrefour',
    'Connect roads':'Raccorder des routes','Cancel connection':'Annuler le raccordement','Connect here':'Raccorder ici',
    'Choose a free endpoint A or B, then click the target road. A shared junction connects routing; street ID grouping is separate.':'Choisissez l’extrémité libre A ou B, puis cliquez sur la route cible. Un nœud commun assure la connexion ; le regroupement des identifiants est distinct.',
    'Click the target road at the junction to connect this endpoint.':'Cliquez sur la route cible à l’endroit du raccordement.',
    'Choose endpoint A or B. Orange endpoints are free; a junction already connects roads.':'Choisissez A ou B. Une extrémité orange est libre ; un carrefour relie déjà des routes.',
    'Roads connected at a shared junction.':'Routes raccordées à un nœud commun.',
    'These roads already share a junction. No connection change is needed.':'Ces routes partagent déjà un nœud. Aucun raccordement nécessaire.',
    'This endpoint already belongs to a junction. Choose a free endpoint.':'Cette extrémité appartient déjà à un carrefour. Choisissez une extrémité libre.',
    'Remove part of a road':'Supprimer une portion de route','Reshape an existing road':'Ajuster une route existante',
    'Choose two positions along this section. The portion between them appears in red; the rest stays.':'Choisissez deux points sur ce tronçon. La portion entre eux apparaît en rouge ; le reste est conservé.',
    'Delete red portion':'Supprimer la portion rouge','Reset cut points':'Replacer les points de coupe','Cancel':'Annuler','Save':'Enregistrer','Done':'Terminer','Remove':'Retirer','Restore':'Restaurer',
    'selected':'sélectionné(s)','outside parts retained. A gap can disconnect the network.':'portions conservées. Une coupure peut déconnecter le réseau.',
    'to remove;':'à supprimer ;','of 2 cut points chosen.':'points de coupe choisis sur 2.',
    'Selected section removed.':'Tronçon sélectionné supprimé.','Selected portion removed; outside pieces retained.':'Portion supprimée ; les parties extérieures sont conservées.',
    'Delete street edges':'Supprimer des tronçons','Click edges to select them (red). Click a grey dashed edge to restore it.':'Cliquez sur les tronçons à supprimer (rouge). Cliquez sur un tronçon gris en pointillés pour le restaurer.',
    'Clear selection':'Effacer la sélection','One undo step; the ids update by themselves.':'Une seule étape d’annulation ; les identifiants se mettent à jour.',
    'Colour by':'Colorer par','one colour':'couleur unique','file':'fichier','Add streets from a file':'Importer des routes',
    'access':'acc\u00e8s','car':'voiture','motorcycle':'moto','foot (dashed)':'\u00e0 pied (tirets)','unknown (dotted)':'inconnu (pointill\u00e9)',
    'Road access':'Acc\u00e8s aux routes','Classify a stretch':'Classer un trajet','Classify access from here (A → B)':'Classer l’accès depuis ici (A → B)','Access class':'Type d\u2019acc\u00e8s',
    'Car':'Voiture','Motorcycle':'Moto','Foot':'\u00c0 pied','Unknown':'Inconnu','Other route':'Autre itin\u00e9raire','Use shortest route':'Utiliser l\u2019itin\u00e9raire le plus court',
    'Save classification':'Enregistrer le classement','Choose A and B again':'Rechoisir A et B','Choose A again':'Rechoisir A',
    'Choose A and B; the tool follows existing edges and never changes geometry or street IDs.':'Choisissez A et B ; l\u2019outil suit les tron\u00e7ons existants sans modifier la g\u00e9om\u00e9trie ni les identifiants.',
    'Click A on or near a road. It will snap to the nearest network node.':'Cliquez sur A, sur une route ou pr\u00e8s d\u2019elle. Le point sera accroch\u00e9 au n\u0153ud le plus proche.',
    'Now click B. The shortest existing route will be calculated without moving or splitting roads.':'Cliquez maintenant sur B. L\u2019itin\u00e9raire existant le plus court sera calcul\u00e9 sans d\u00e9placer ni couper les routes.',
    'No other node-distinct route exists between A and B.':'Aucun autre itin\u00e9raire distinct par les n\u0153uds n\u2019existe entre A et B.',
    'This changes access only. Geometry and street IDs remain unchanged.':'Seul l\u2019acc\u00e8s est modifi\u00e9. La g\u00e9om\u00e9trie et les identifiants restent inchang\u00e9s.',
    'Road access saved.':'Acc\u00e8s routier enregistr\u00e9.',
    'Click anchor A before the incorrect portion, then anchor B after it, also further along the road.':'Cliquez sur l’ancre A avant la partie incorrecte, puis sur l’ancre B après elle, même plus loin sur la route.',
    'Drivable from A to B':'Carrossable de A \u00e0 B','Set drivable from A to B':'D\u00e9finir carrossable de A \u00e0 B','Set drivable from here (A \u2192 B)':'D\u00e9finir carrossable depuis ici (A \u2192 B)',
    'Yes':'Oui','No (foot or motorbike)':'Non (\u00e0 pied ou \u00e0 moto)','Drivable saved.':'Carrossable enregistr\u00e9.','OSM track':'piste OSM',
    'no car access, may continue on foot or by motorbike':'pas d\u2019acc\u00e8s en voiture, possible \u00e0 pied ou \u00e0 moto','unknown: follows the road type (dotted)':'inconnu : selon le type de route (pointill\u00e9)',
    'This changes drivable only; roads do not move. Street IDs are recalculated at the next Compute.':'Seul le caract\u00e8re carrossable change ; les routes ne bougent pas. Les identifiants sont recalcul\u00e9s au prochain calcul.',
    'Choose A and B; the tool follows existing roads and never moves them. Colour by drivable in the Street types and IDs tab to check; OSM tracks are named in the tooltip.':'Choisissez A et B ; l\u2019outil suit les routes existantes sans les d\u00e9placer. Colorez par carrossable dans l\u2019onglet Types et identifiants des rues pour v\u00e9rifier ; les pistes OSM sont indiqu\u00e9es dans l\u2019infobulle.',
    'Click B. Both points will snap to the nearest network node.':'Cliquez sur B. Les deux points seront accroch\u00e9s au n\u0153ud du r\u00e9seau le plus proche.',
    'Draw, prolong or reshape a road':'Dessiner, prolonger ou ajuster','Trace route: start → end':'Tracer : départ → arrivée','Draw a new road':'Dessiner une route',
    'Prolong a road end':'Prolonger une route','Delete edges':'Supprimer des tronçons','Remove part of a road...':'Supprimer une portion…','Select whole edges to delete...':'Sélectionner des tronçons entiers…',
    'Street data and Google Earth':'Données des rues et Google Earth','⬇ Street data CSV':'⬇ Données des rues CSV','⬇ Streets KML':'⬇ Routes KML',
    'Upload an edited street data CSV (rank, drivable, paved):':'Importer un CSV modifié (classe, praticabilité, revêtement) :','Files already added':'Fichiers importés',
    'Edit connections':'Vérifier les connexions','new road':'nouvelle route','downloaded network (OSM)':'réseau téléchargé (OSM)',
    'Drawing':'Dessin','Click points':'Points successifs','Freehand trace':'Tracé à main levée','Snap to existing roads':'Accrocher aux routes existantes',
    'Stop here: path beyond this point is unclear':'Arrêter ici : le chemin au-delà est incertain','Finish':'Terminer','Finish and recompute ids':'Terminer et recalculer',
    'Undo last stroke':'Annuler le dernier trait','Reset draft':'Réinitialiser le tracé','Remove last point':'Retirer le dernier point','Enter finishes · Esc cancels':'Entrée : terminer · Échap : annuler',
    'Name (optional)':'Nom (facultatif)','Rank':'Classe','Drivable':'Carrossable','Paved':'Revêtue','yes':'oui','no':'non','unknown':'inconnu',
    'New road':'Nouvelle route','Prolong a road':'Prolonger une route','Reshape road':'Ajuster une route','Trace a connected route':'Tracer un itinéraire continu',
    'Move the white points or insert bends between the fixed junctions. Orange shows the previous shape. Freehand replaces the interior; trace from the first endpoint toward the last. Saving does not add another road. A crossing does not create a new junction.':'Déplacez les points blancs ou ajoutez des virages entre les extrémités fixes. L’orange indique l’ancien tracé. Le tracé libre remplace l’intérieur, du départ vers l’arrivée. Un croisement ne crée pas automatiquement un carrefour.',
    'Click a dead end (orange dot) of the road to prolong.':'Cliquez sur l’extrémité libre (point orange) de la route à prolonger.',
    'Hold the left mouse button and trace the road. Release to adjust the points; Finish saves it.':'Maintenez le bouton gauche pour tracer la route. Relâchez pour ajuster les points ; Terminer enregistre le tracé.',
    'Drag the white points to follow the visible road. Click a small midpoint to insert a bend; right-click a white point to remove it.':'Déplacez les points blancs le long du chemin visible. Cliquez sur un petit point intermédiaire pour ajouter un virage ; clic droit sur un point blanc pour le retirer.',
    'Click along the road to add bends. Drag a point to reshape; click a small midpoint to insert a bend; right-click a point to remove it.':'Cliquez le long de la route pour ajouter des virages. Déplacez un point pour ajuster ; cliquez sur un point intermédiaire pour ajouter un virage ; clic droit pour retirer un point.',
    'Current road endpoint':'Extrémité actuelle','Right-click its road and choose Connect an endpoint to a road. This works on the current cut and corrected sections.':'Faites un clic droit sur sa route et choisissez Raccorder une extrémité à une route. Cet outil utilise les tronçons actuels, coupés ou corrigés.',
    'Choose the reference point':'Choisir le point de référence','Click the map near the node the numbering starts from (for example a crossroads).':'Cliquez près du nœud où commence la numérotation, par exemple un carrefour.',
    'Move over the map: the highlighted node is the one you get. Click to select it.':'Déplacez le curseur : le nœud en surbrillance sera sélectionné. Cliquez pour le choisir.',
    'Keep the current point':'Conserver le point actuel','Yes, use it':'Oui, utiliser ce point','No, choose another':'Non, en choisir un autre',
    'Is this the right place?':'Est-ce le bon emplacement ?','Yes, confirm it':'Oui, confirmer','No, I will move it':'Non, déplacer le point',
    'the default point of this project':'le point par défaut de ce projet','set by another editor':'défini par un autre éditeur','Reference point confirmed':'Point de référence confirmé',
    'Settings':'Paramètres','Apply settings':'Appliquer','Derivation levels':'Niveaux de noms dérivés','House step (m)':'Pas des numéros de maison (m)','Sub-street step (m)':'Pas des rues secondaires (m)',
    'Houses farther than (m) from a road get no address':'Distance maximale d’adressage depuis une route (m)',
    'Computing the street ids...':'Calcul des identifiants…','Edits not applied yet':'Modifications à appliquer','Recompute ids':'Recalculer les identifiants',
    'Updating the map':'Mise à jour de la carte','Loading the completed map':'Chargement de la carte terminée',
    'The current map stays visible until the update is ready.':'La carte actuelle reste visible jusqu’à ce que la mise à jour soit prête.',
    'streets':'rues','original ids':'identifiants d’origine','new ids from cutting':'nouveaux identifiants après découpe','cut points':'points de découpe',
    'street id':'identifiant de rue','distance to the reference':'distance au point de référence','street rank':'classe de route','drivable':'carrossable','paved':'revêtue',
    'Streets to name, in priority order':'Rues à nommer, par priorité','street':'rue','name':'nom','covers':'couvre','why':'raison','nothing left to name':'aucune rue à nommer',
    'show fewer':'afficher moins','Name of this street':'Nom de cette rue','Name saved.':'Nom enregistré.','Name deleted':'Nom supprimé','Name removed':'Nom retiré',
    'House numbers, addresses and street signs':'Numéros de maison, adresses et plaques de rue','Search an address...':'Rechercher une adresse…',
    'Click a building to see its address, side of the road and road point.':'Cliquez sur un bâtiment pour voir son adresse, son côté de rue et son accès.',
    'Choose the road point':'Choisir le point d’accès','Nearest road':'Route la plus proche','Back to the nearest road.':'Retour à la route la plus proche.',
    'Street names — Fotouni':'Noms des rues — Fotouni','Streets that need a name':'Rues à nommer','type the name':'saisir le nom',
    'Click a red street on the map or in this list, type its name and press Enter.':'Cliquez sur une rue rouge sur la carte ou dans la liste, saisissez son nom et appuyez sur Entrée.',
    'Every street has a name. Thank you!':'Toutes les rues ont un nom. Merci !','has a name':'nom attribué','name follows from another street':'nom dérivé d’une autre rue','needs a name':'à nommer',
    '(empty = no name)':'(vide = aucun nom)','(no name yet)':'(sans nom)','no address yet':'pas encore d’adresse','no address yet: the street has no name':'pas d’adresse : la rue n’a pas de nom',
    'search an address or a name':'rechercher une adresse ou un nom','⬇ Street names (CSV)':'⬇ Noms des rues (CSV)','⬇ Addresses (CSV)':'⬇ Adresses (CSV)',
    'Something went wrong':'Une erreur est survenue','Loading…':'Chargement…','Saving…':'Enregistrement…','Saved':'Enregistré',
    'Edits are saved at once. Restoring adds a checkpoint (undoable).':'Les modifications sont enregistrées immédiatement. La restauration crée une étape annulable.',
    'Describe this checkpoint (optional):':'Décrivez cette étape (facultatif) :','Satellite':'Satellite','OpenStreetMap':'OpenStreetMap','Background opacity':'Opacité du fond de carte',
    'Prepare the roads':'Préparer les routes','Check street identity':'Vérifier les identifiants','Give places a name':'Nommer les lieux','Review house access':'Vérifier les accès aux maisons',
    'Follow visible paths, keep junctions connected, and flag uncertain ends.':'Suivez les chemins visibles, raccordez les carrefours et signalez les extrémités incertaines.',
    'Select a junction to split or group segments into a street.':'Sélectionnez un carrefour pour séparer ou regrouper des tronçons.',
    'Name priority streets so smaller streets can inherit a clear address.':'Nommez les rues prioritaires pour donner des adresses claires aux rues secondaires.',
    'Select a building to check its address and choose the correct road access.':'Sélectionnez un bâtiment pour vérifier son adresse et choisir le bon accès.',
    'Right-click a road to edit':'Clic droit sur une route pour la modifier',
    'Your edits are saved automatically. Use checkpoints before a larger change.':'Vos modifications sont enregistrées automatiquement. Créez une étape avant une modification importante.',
    'Street':'Rue','Name of street':'Nom de la rue','original id':'identifiant d’origine','length':'longueur','distance to reference':'distance à la référence','derived from':'dérivée de',
    'street cut here for the numbering':'rue divisée ici pour la numérotation','new id (split here)':'nouvel identifiant (séparer ici)',
    'Not connected to the main network: draw or prolong a road to connect it, or delete it.':'Ce tronçon est déconnecté du réseau principal : dessinez ou prolongez une route pour le raccorder, ou supprimez-le.',
    'Delete this part':'Supprimer cette partie','updating...':'mise à jour…','loading...':'chargement…','Applies to this part only.':'S’applique uniquement à cette partie.',
    'Set name':'Enregistrer le nom','Back to the OSM name':'Revenir au nom OSM','Delete name':'Supprimer le nom',
    'this name is already used by another street':'ce nom est déjà utilisé pour une autre rue','Saved at once; the street ids update by themselves.':'Enregistré immédiatement ; les identifiants se mettent à jour.',
    'none':'aucun','Second-level names (x-y-name) for drive roads shorter than (m)':'Noms de second niveau (x-y-nom) pour les routes carrossables de moins de (m)',
    'named streets must connect to the reference through named streets':'les rues nommées doivent rejoindre la référence par des rues nommées',
    'This project has no houses to address (input/buildings.gpkg).':'Ce projet ne contient aucune maison à adresser (input/buildings.gpkg).',
    'Rank = how important a point is for the signs.':'La classe indique l’importance d’un lieu pour la signalisation.',
    'sign rank':'importance pour les panneaux','Selected node':'Nœud sélectionné','Use the suggestion':'Utiliser la suggestion','keep the existing':'conserver l’existant',
    'lines in the file':'lignes dans le fichier','connection nodes':'nœuds de connexion','ends not connected':'extrémités libres','roads not reaching the network':'routes hors du réseau principal',
    'existing roads replaced':'routes existantes remplacées','Click a node to connect or disconnect it. Nothing is saved until you accept.':'Cliquez sur un nœud pour le raccorder ou le déconnecter. Rien n’est enregistré avant votre validation.',
    'Replaced roads':'Routes remplacées','Same end nodes and a length within 10 %: the new street wins. Tick the ones that must stay.':'Mêmes extrémités et longueur à 10 % près : la nouvelle route remplace l’ancienne. Cochez celles à conserver.',
    'Connect ends with a suggestion':'Raccorder les extrémités suggérées','Each stroke must start at the last point. The planned end remains separate until reached. Stop and flag uncertainty where the visible path disappears.':'Chaque trait doit commencer au dernier point. L’arrivée prévue reste distincte tant qu’elle n’est pas atteinte. Arrêtez-vous et signalez l’incertitude là où le chemin disparaît.',
    'The network is not connected':'Le réseau est déconnecté','Connection of the added streets':'Connexions des routes ajoutées','ends connected automatically':'extrémités raccordées automatiquement',
    'roads split to connect':'routes divisées pour le raccordement','Right-click a current road to connect its endpoint.':'Clic droit sur une route actuelle pour raccorder son extrémité.',
    'Connect the ends with a suggestion (≤ 25 m)':'Raccorder les extrémités suggérées (≤ 25 m)',
    'The street ids update by themselves. Click a node of a new road to edit its connection.':'Les identifiants se mettent à jour. Cliquez sur un nœud d’une nouvelle route pour modifier sa connexion.',
    'Ends not connected':'Extrémités libres','nearest existing road':'route existante la plus proche','all ends are connected':'toutes les extrémités sont raccordées',
    'KML, GeoJSON, GeoPackage or zipped shapefile':'KML, GeoJSON, GeoPackage ou shapefile compressé',
    'Reshape existing road':'Ajuster une route existante','Click the starting point.':'Cliquez sur le point de départ.',
    'Click the planned ending point. This does not draw a connecting line.':'Cliquez sur l’arrivée prévue. Aucune ligne de raccordement n’est encore créée.',
    'points. Freehand mode uses dragging to draw; switch to Click points to pan the map.':'points. Maintenez le bouton pour dessiner à main levée ; passez aux Points successifs pour déplacer la carte.',
    'Existing junctions stay fixed.':'Les carrefours existants restent fixes.','With snapping off, new ends stay unconnected.':'Sans accrochage, les nouvelles extrémités restent libres.',
    '0 motorway / trunk':'0 autoroute / voie rapide','1 primary':'1 principale','2 secondary':'2 secondaire','3 tertiary':'3 tertiaire','4 residential / service':'4 résidentielle / desserte','5 footway / path':'5 sentier / chemin',
    '0 not on the signs':'0 sans panneau','1 landmark':'1 repère','2 important':'2 important','3 local':'3 local',
    'Move this endpoint {0} m to the target road and create a shared junction? Street IDs are preserved.':'Déplacer cette extrémité de {0} m vers la route cible et créer un nœud commun ? Les identifiants sont conservés.',
    'Delete only the red {0} m? This may create a network gap. You can Undo.':'Supprimer uniquement les {0} m en rouge ? Cela peut déconnecter le réseau. Vous pourrez annuler.',
    'Use this node ({0}) as the reference point? The numbering of every street and house starts here.':'Utiliser ce nœud ({0}) comme référence ? La numérotation des rues et des maisons commence ici.',
    'The numbering of every street and house starts at the star on the map: {0}, {1}.':'La numérotation des rues et des maisons commence à l’étoile sur la carte : {0}, {1}.',
    'A: {0} · B: {1}':'A : {0} · B : {1}',
    'Selected road: {0} m · A: {1} · B: {2}':'Route choisie : {0} m · A : {1} · B : {2}',
    'Delete the {0} selected':'Supprimer les {0} tronçons choisis',
    'Move over the map: the highlighted node is where the reference point goes. Click to choose it - the numbering starts from that node.':'Déplacez le curseur : le nœud en surbrillance sera la référence. Cliquez pour le choisir ; la numérotation commencera à ce nœud.',
    'Click the existing road or node this end must connect to.':'Cliquez sur la route ou le nœud auquel raccorder cette extrémité.',
    'Click two positions on the selected road. Only the red preview between them will be removed.':'Cliquez sur deux points de la route choisie. Seule la portion rouge entre eux sera supprimée.',
    'Click a road next to house {0}: its number will be taken from that point.':'Cliquez sur la route près de la maison {0} : ce point servira à calculer son numéro.',
    'No current road section here. Zoom in and right-click closer to the line.':'Aucun tronçon actuel ici. Zoomez et faites un clic droit plus près de la ligne.',
    'Click a dead end (orange dot) first':'Cliquez d’abord sur une extrémité libre (point orange)',
    'REFERENCE POINT':'POINT DE RÉFÉRENCE','Click a street':'Cliquez sur une rue','or a white node':'ou un nœud blanc','on the map: a popup opens.':'sur la carte pour ouvrir ses options.',
    'last edit {0}':'dernière modification {0}','no edits yet':'aucune modification',
    'checkpoint "{0}" {1}':'étape « {0} » {1}','Computed: {0} streets':'Calcul terminé : {0} rues',
    'updating the street ids...':'mise à jour des identifiants…','updating the addresses...':'mise à jour des adresses…','choose the reference point':'choisir le point de référence',
    'street needs':'rue nécessite','streets need':'rues nécessitent','a name (red). Naming them lets the others derive theirs.':'un nom (en rouge). Les autres rues pourront en dériver le leur.',
    'Planner':'Planificateur','minimum proven on the final cut network':'minimum prouvé sur le réseau final découpé','feasible final plan; minimum not proven':'plan final valide ; minimum non prouvé',
    'routing rounds':'itérations de routage','task removed by final optimisation':'tâche retirée par l’optimisation finale','tasks removed by final optimisation':'tâches retirées par l’optimisation finale',
    'Street name (empty = no name)':'Nom de rue (vide = aucun nom)',
    'Click a building to see its address. Buildings in red have no address yet because their street has no name: give it a name in':'Cliquez sur un bâtiment pour voir son adresse. Les bâtiments rouges n’ont pas encore d’adresse car leur rue n’est pas nommée. Nommez-la dans',
    'has a name \u00a0':'nom attribué \u00a0',
    'Naming rules: highways, primary and secondary roads always need their own name; other roads may take one derived name (Voie 3 du xyz), never two levels (Voie 3/3 du xyz).':'Règles de nommage : les routes nationales, primaires et secondaires ont toujours leur propre nom ; les autres routes peuvent prendre un nom dérivé (Voie 3 du xyz), jamais sur deux niveaux (Voie 3/3 du xyz).'
    ,'Approved address rule: a house number represents metres from the street start; a branch prefix represents tens of metres.':'Règle d’adressage approuvée : le numéro d’une maison représente les mètres depuis le début de la rue ; le préfixe d’une voie secondaire représente les dizaines de mètres.'
    ,'Metres per house number':'Mètres par numéro de maison','Metres per branch prefix':'Mètres par préfixe de voie secondaire'
  };
  let language='en';
  try { language=localStorage.getItem('address-language') || (navigator.language.startsWith('fr')?'fr':'en'); } catch (_) { /* browser storage may be disabled */ }
  if (!['en','fr'].includes(language)) language='en';
  const t = text => language==='fr' && Object.hasOwn(fr,text) ? fr[text] : text;
  function text(value) {
    const match=value.match(/^(\s*)([\s\S]*?)(\s*)$/),raw=match[2];
    const decoder=document.createElement('textarea'); decoder.innerHTML=raw;
    const translated=t(decoder.value);
    if (translated===decoder.value) return value;
    return match[1]+translated.replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))+match[3];
  }
  function markup(part) {
    if (language==='en') return part;
    // Called on literal template parts BEFORE user values are inserted.
    return part.replace(/(^|>)([^<>]*)(?=<|$)/g,(_,prefix,body)=>prefix+text(body))
      .replace(/\b(placeholder|title|aria-label)="([^"<>]*)"/g,(_,attr,value)=>`${attr}="${text(value)}"`);
  }
  const html=(parts,...values)=>parts.reduce((out,part,i)=>out+markup(part)+(i<values.length?values[i]:''),'');
  const msg=(parts,...values)=>t(parts.reduce((out,part,i)=>out+part+(i<values.length?`{${i}}`:''),''))
    .replace(/\{(\d+)\}/g,(_,i)=>String(values[+i]));
  function warning(w) {
    if(language!=='fr') return w;
    const n=w.count ?? w.streets?.length ?? 0,ids=(w.streets || []).join(', ');
    const labels={
      stale_cuts:['Modifications de routes à vérifier','Une route source a changé ou disparu. Vérifiez les anciennes coupes ou connexions avant d’utiliser le réseau.'],
      path_uncertain:[`${n} extrémité(s) de chemin à vérifier`,'Le tracé s’arrête là où le chemin est incertain. Ne supposez pas de connexion au-delà.'],
      roads_dangling:[`${n} extrémité(s) libre(s)`,'Certaines sont des impasses normales. Pour raccorder une extrémité, faites un clic droit sur sa route.'],
      roads_isolated:[`${n} route(s) hors du réseau principal`,'Vérifiez leur emplacement et les connexions au réseau principal.'],
      needs_name:[`${n} rue(s) à nommer`,'Ces rues apparaissent en rouge. Les nommer permet aux autres de recevoir des noms dérivés.'],
      uncovered:[`${n} rue(s) nécessitent leur propre nom`,`Vérifiez et nommez les rues concernées : ${ids}.`],
      unconnected:[`${n} rue(s) nommée(s) ne rejoignent pas la référence`,'Vérifiez les connexions et la continuité des rues nommées.']
    };
    let pair=labels[w.code];
    // Translate the authored prefix only; preserve every supplied place name.
    if(w.code==='duplicate_name') pair=[w.title.replace(/^Name used for (\d+) streets: /,'Nom utilisé pour $1 rues : '),`Identifiants : ${ids}. Vérifiez s’il faut regrouper ces rues ou leur donner des noms distincts.`];
    if(w.code==='named_split') pair=[w.title.replace(/^Named street split: /,'Rue nommée divisée : '),`Cette rue a été divisée pour la numérotation. Vérifiez les parties : ${ids}.`];
    if(w.code==='short_part') pair=[w.title.replace(/^Very short part of /,'Portion très courte de '),`Vérifiez cette petite portion et son identifiant : ${ids}.`];
    return pair?{...w,title:pair[0],message:pair[1]}:w;
  }
  const originals=[];
  function captureStatic() {
    const walker=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);
    while (walker.nextNode()) {
      const n=walker.currentNode;
      if (n.parentElement.closest('script,style,#project-name,#save-state,#state,#map')) continue;
      if (n.textContent.trim()) originals.push([n,n.textContent]);
    }
    document.querySelectorAll('[title],[aria-label],[placeholder]').forEach(el=>{
      for (const attr of ['title','aria-label','placeholder']) if (el.hasAttribute(attr)) el.setAttribute('data-original-'+attr,el.getAttribute(attr));
    });
  }
  function applyStatic() {
    document.documentElement.lang=language;
    originals.forEach(([n,original])=>{if(n.isConnected) n.textContent=original.replace(/^(\s*)(.*?)(\s*)$/s,(_,a,b,c)=>a+t(b)+c);});
    document.querySelectorAll('[data-original-title],[data-original-aria-label],[data-original-placeholder]').forEach(el=>{
      for (const attr of ['title','aria-label','placeholder']) if(el.hasAttribute('data-original-'+attr)) el.setAttribute(attr,t(el.getAttribute('data-original-'+attr)));
    });
    const select=document.getElementById('language-select'); if(select) select.value=language;
  }
  function setLanguage(value) {
    if (!['en','fr'].includes(value)) return;
    language=value; try {localStorage.setItem('address-language',value);} catch (_) { /* optional persistence */ }
    applyStatic(); window.dispatchEvent(new CustomEvent('languagechange'));
  }
  captureStatic(); applyStatic();
  document.getElementById('language-select')?.addEventListener('change',e=>setLanguage(e.target.value));
  return {t,html,msg,warning,htmlText:markup,setLanguage,get language(){return language;}};
})();
