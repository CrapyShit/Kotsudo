# Le rig de Murakami, expliqué simplement

Version française de `murakami-rig-explained-simple.md`. Même contenu, même
niveau de détail. Chaque mot technique est expliqué la première fois qu'il
apparaît, avec des comparaisons de la vie courante quand ça aide.

**L'histoire en bref :** on a construit un traducteur. Il lit un personnage
riggé dans Maya et reconstruit le même rig, qui fonctionne de la même façon,
dans Unreal Engine. Ensuite on a construit un testeur : il fait bouger les
deux rigs de la même manière et mesure l'écart entre les deux. On a corrigé
jusqu'à ce qu'ils correspondent.

Le résultat : pour chacune des 21 parties du personnage, Unreal et Maya
correspondent à **1 millimètre** près (0,1 cm), sur les 290 poses de test.

---

## Partie A : le vocabulaire (à lire en premier)

**Articulation / os (joint / bone).** Les pièces du squelette. Maya dit
*joint*, Unreal dit *bone* : c'est la même chose. Murakami a des
articulations comme `Spine1` (colonne), `L_LegLeaf2` (jambe gauche, 2e
articulation = le genou) et `Head` (la tête).

**Skin / skinning.** Le fait d'attacher la surface 3D du personnage (le
maillage, *mesh*) au squelette, pour que la surface bouge quand les os
bougent.

**Pose de liaison (bind pose).** La pose du squelette au moment où la peau a
été attachée. Comme la photo prise le jour où les vêtements ont été cousus.

**Pose de repos (rest pose).** La pose dans laquelle le rig se trouve quand
personne ne touche aux contrôleurs. En général identique à la pose de
liaison, *mais pas toujours* (ça a compté pour l'orteil).

**Contrôleur (controller / control).** Les courbes de couleur que
l'animateur attrape et déplace (cercles, boîtes…). Les contrôleurs font
bouger les articulations ; l'animateur ne touche jamais directement les
articulations.

**Pivot.** Le point autour duquel un contrôleur tourne, comme la charnière
d'une porte. Si le pivot est au mauvais endroit, la porte tourne mal.

**Décalage (offset).** La distance entre deux choses qui bougent ensemble.
Par exemple, « le contrôleur est 7 cm devant son articulation ».

**FK (cinématique directe, *Forward Kinematics*).** On tourne chaque
articulation soi-même, l'une après l'autre : épaule, puis coude, puis
poignet. Comme on règle une lampe de bureau à la main.

**IK (cinématique inverse, *Inverse Kinematics*).** On ne déplace que le bout
(la main ou le pied). L'ordinateur calcule tout seul comment le coude ou le
genou doit se plier pour y arriver. Comme quand on tire la main d'une
marionnette : le bras suit tout seul.

**Interrupteur IK/FK (IK/FK switch).** Un curseur qui choisit entre IK et FK
pour un bras ou une jambe. Sur Murakami : `IK_FK = 0` veut dire IK, `1` veut
dire FK.

**Pole vector.** Un petit contrôleur qui indique à l'IK dans quelle direction
le coude ou le genou doit pointer. Comme dire au genou « pointe vers ce
mur-là ».

**Spline IK.** Pour la colonne vertébrale : une courbe lisse longe le dos, et
les articulations de la colonne sont posées le long de cette courbe. On plie
la colonne en déplaçant quelques contrôleurs qui donnent sa forme à la
courbe. Comme un tuyau d'arrosage qu'on plie en bougeant les quelques mains
qui le tiennent.

**Point de courbe (CV).** Les points qui donnent sa forme à une courbe. Chaque
point est tiré par les contrôleurs de la colonne, certains plus, d'autres
moins. Ces proportions s'appellent les **poids** (par exemple 70 % poitrine,
30 % milieu du dos).

**Contrainte (constraint).** Une règle du type « cette chose suit cette
autre chose ». Exemple : « Spine4 tourne comme le contrôleur de la
poitrine. »

**Parent / enfant.** Un enfant suit son parent : si on bouge le parent,
l'enfant vient avec (la main suit l'avant-bras). L'**espace parent** d'un
contrôleur, c'est ce qu'il suit.

**Null.** Un point d'aide invisible dans Unreal. Il garde une position et peut
suivre des choses. On s'en sert comme crochet, poignée invisible ou
intermédiaire.

**Manifeste (manifest).** La description écrite de tout le rig, produite par
Maya : chaque module, contrôleur, pivot, poids et contrainte. Unreal le lit
pour reconstruire le rig. C'est le plan de construction.

**Module.** Une partie du rig, construite d'un seul bloc : la colonne, le
cou, chaque bras, chaque jambe, l'orteil, les yeux, chaque pétale.

**Control Rig.** Le système d'Unreal pour construire des rigs : des
contrôleurs, des nulls, et un « graphe » de petites boîtes de calcul (des
*nœuds*) reliées entre elles, qui s'exécute à chaque image.

**Test de poses (pose check / harness).** Notre testeur. Il met le rig Maya
dans des centaines de poses, rejoue les mêmes poses sur le rig Unreal et
mesure la différence.

**Unités.** Unreal travaille en **centimètres**. La scène Maya de Murakami
travaille en **mètres**. Murakami est immense : environ 16 m de haut, les
jambes seules font environ 6 m.

**T0 / T1 (les notes du rapport).**
- **T0** = écart de moins de 0,01 cm (un dixième de millimètre) : parfait.
- **T1** = moins de 0,1 cm (1 mm) et 0,5° : notre objectif, « identique à
  Maya ».
- **au-dessus de T1** = quelque chose à regarder.

---

## Partie B : tout le trajet en 5 étapes

```
 MAYA                                              UNREAL
 1. Tagger : « ces articulations sont la colonne,
    celles-ci le bras gauche... »
 2. Le bouton d'export produit :
    - le fichier du personnage (FBX)      --->  3. Import du FBX
      avec le plan de construction                4. Le builder lit le plan et
      (manifeste) caché à l'intérieur                construit chaque partie du rig
    - les formes des contrôleurs en
      petits fichiers 3D
    - le fichier des poses de test        --->  5. Le testeur rejoue les poses
                                                    et écrit le rapport
```

1. **Tagger** (`rig_tagger_tool.py`). Dans Maya, on étiquette des groupes
   d'articulations : « Spine1 à Spine4 = colonne, type spline »,
   « L_LegLeaf1 à 3 = jambe gauche, type IK/FK »…
2. **Export** (`export_rig_manifest.py`). Il écrit :
   - le **FBX**, le fichier standard avec le squelette et la peau. Le plan de
     construction est caché dedans, stocké comme du texte sur l'articulation
     racine.
   - les **formes des contrôleurs**, un petit fichier 3D par forme
     (`murakami_shapes/RB_xxxx.fbx`).
   - les **poses de test** (`murakami.poses.json`).
3. **Import** du FBX dans Unreal.
4. **Builder** (`run_rig_builder.py`). Il lit le plan et construit chaque
   partie dans un Control Rig.
5. **Testeur** (`pose_harness.py`). Il se lance automatiquement et écrit
   `murakami.harness_report.json` (et un `.html` à ouvrir dans un
   navigateur).

---

## Partie C : ce dont toutes les parties dépendent

### C1. Traduire les directions et les tailles

Maya et Unreal ne sont pas d'accord sur deux choses de base :

- **Où est le haut.** Dans Maya, le haut c'est l'axe Y ; dans Unreal c'est Z.
  Chaque direction est donc traduite : Maya (X, Y, Z) devient Unreal
  (X, Z, Y). Les rotations subissent la même traduction.
- **Les unités.** Unreal travaille en cm, la scène Maya de Murakami en mètres.

**Ce qui n'allait pas :** Maya répond en centimètres ou en mètres selon *la
façon* dont on lui pose la question :
- demander une « matrice » (un paquet complet position + rotation) répond
  toujours en **cm** ;
- demander une « translation » ou un « pivot » répond dans l'unité de la
  scène, ici en **mètres**.

Notre exporteur mélangeait les deux, donc certaines distances sortaient
**100 fois trop grandes ou trop petites**.

**La correction :** chaque valeur est maintenant lue de la bonne façon, avec
la bonne unité. Unreal vérifie aussi chaque décalage de contrôleur deux fois,
sous deux formes différentes. Si les deux longueurs ne sont pas d'accord, il
refuse et le signale, au lieu de placer en silence un contrôleur au mauvais
endroit.

### C2. Comment un contrôleur est décrit

Pour chaque contrôleur Maya, le plan enregistre :

- **Son pivot (le point autour duquel il tourne).** On prend le vrai pivot du
  contrôleur. Seule exception : si le pivot a été laissé au centre du monde
  (signe que personne ne l'a réglé), on prend le milieu de la forme à la
  place.
- **La position de ce pivot, mesurée depuis une articulation proche
  (l'« ancre »).** Elle est enregistrée deux fois :
  - une fois comme une direction dans le monde (« 7 cm vers l'avant ») ;
  - une fois du point de vue de l'articulation elle-même (« 7 cm sur le côté
    de l'articulation »).

  Chaque version est vérifiée avec une autre articulation proche. Si les deux
  sont d'accord, parfait. Sinon, la version « monde » gagne et un
  avertissement s'affiche.
- **Son orientation, sa couleur, sa taille et ses canaux verrouillés,** plus
  ses curseurs personnalisés. Ils deviennent aussi des curseurs sur le
  contrôleur Unreal.
- **Ce qu'il suit (ses parents).** La hiérarchie des contrôleurs dans Maya.
  Si une contrainte le pilote, le plan enregistre ce que cette contrainte
  suit (voir partie F).

**L'astuce du crochet (driver null).** Souvent, un contrôleur flotte à côté de
son articulation : un grand cercle devant la main, un pivot placé à côté de
l'os. Dans Unreal, on place le contrôleur exactement où il est dans Maya.
Puis on accroche dessous un crochet invisible (un null appelé
`<contrôleur>_Drv`), posé exactement sur l'articulation. Quand le contrôleur
bouge, le crochet bouge avec lui, et l'articulation copie le crochet. Le
contrôleur peut donc être n'importe où, l'articulation tombe quand même au
bon endroit.

### C3. Les formes des contrôleurs (les courbes deviennent des tubes 3D)

Unreal ne sait pas dessiner directement les courbes de Maya. Donc :

1. L'exporteur échantillonne chaque courbe en une suite de points (en cm,
   directions Unreal), centrés sur le pivot du contrôleur.
2. Il entoure ces points d'un tube carré très fin, comme un fil de fer, et
   enregistre chaque forme dans son propre petit fichier 3D. Les formes
   identiques ne sont enregistrées qu'une fois (chacune reçoit un nom
   calculé à partir de son contenu).
3. Unreal importe ces tubes et les enregistre comme formes de contrôleurs. La
   forme d'un contrôleur est stockée « face au monde », donc Unreal annule la
   rotation propre du contrôleur en la dessinant. Le résultat est identique à
   Maya.

Si une forme ne peut pas être importée, Unreal prend à la place un cercle,
une boîte ou une sphère standard de la bonne taille.

### C4. Pose de liaison contre pose de repos (la photo contre la réalité)

Quand Unreal importe le personnage, il construit le squelette à partir de la
**pose de liaison**, la « photo du jour où les vêtements ont été cousus ».
D'habitude c'est aussi la pose de repos du rig. Pas sur Murakami :
- **les orteils** reposent **1,0114 cm plus haut** qu'au moment du skinning.
  Quelqu'un a ensuite décalé le contrôleur du pied de −1,0114 cm pour
  compenser ;
- les hanches et la colonne diffèrent d'un rien (moins de 0,007 cm).

**Ce qu'on voyait :** l'orteil et son contrôleur étaient à 1 cm de leur place
au repos. Tourner le contrôleur de l'orteil le faisait pivoter autour du
mauvais point, avec 0,35 cm d'erreur.

**La correction :** l'exporteur écrit maintenant la **vraie pose de repos** de
Maya pour chaque articulation, en plus de la pose de liaison. Avant de
construire quoi que ce soit, le builder déplace chaque os différent sur la
pose de repos de Maya. Pour la rotation, il n'applique que la *différence*
entre repos et liaison, par-dessus ce qu'Unreal a déjà, donc il ne peut pas
se tromper de convention d'axes. Le journal (log) indique quels os ont été
déplacés.

*Petit bug en plus :* la première version utilisait une fonction d'Unreal
(`inverse()` sur une rotation) qui n'existe pas dans le Python d'Unreal 5.6,
donc ça plantait. On fait maintenant ce calcul nous-mêmes.

---

## Partie D : la colonne vertébrale (spline IK)

### Comment Maya fait
Une courbe lisse longe Spine1–Spine4. Les points de la courbe sont attachés,
avec des poids, à trois **articulations d'aide cachées** :
`Pelvis_IKSplinectrl`, `spine_IKSplinectrl_01` et `chest_IKSplinectrl`.
Chacune est rangée dans un contrôleur d'animateur :
- `Pelvis_IKctrl`
- `spine_ctrl_01`
- `chest_ctrl`

Bouger le contrôleur de la poitrine bouge son articulation d'aide, qui tire
la courbe, qui plie la colonne. En plus, Spine4 *tourne* comme la poitrine
(une contrainte). La colonne de Murakami ne s'étire jamais.

### Ce qu'on envoie
- **Les contrôleurs :** chaque articulation d'aide, nommée d'après le
  contrôleur d'animateur auquel elle appartient, avec la forme, l'orientation
  et le parent de ce contrôleur. Depuis la dernière correction, aussi le
  pivot propre du contrôleur d'animateur.
- **Chaque point de courbe :** sa position et ses poids sur chaque
  contrôleur.
- **Si la colonne s'étire** (détecté dans Maya : non).
- **La règle en plus :** « Spine4 tourne comme la poitrine ».

### Comment Unreal la reconstruit
1. **Un contrôleur par contrôleur d'animateur,** sous son parent Maya.
2. **Les points de courbe (les perles).** Imagine chaque point de courbe comme
   une perle sur un fil. Chaque perle est tirée par les contrôleurs de la
   colonne, mais pas autant par chacun. Par exemple, une perle près de la
   poitrine est tirée à 70 % par le contrôleur de la poitrine, à 30 % par
   celui du milieu du dos, et à 0 % par celui du bassin. Ces pourcentages
   sont les **poids**, copiés de Maya. Unreal recopie l'effet en trois
   étapes :
   - **Un repère invisible par contrôleur qui tire sur la perle.** Notre
     perle d'exemple reçoit deux repères : un pour la poitrine, un pour le
     milieu du dos.
   - **Chaque repère est collé à son contrôleur,** donc il bouge et tourne
     avec lui.
   - **La perle se place entre ses repères, à 70 % vers le repère de la
     poitrine et à 30 % vers celui du milieu du dos.** Par exemple, si le
     repère de la poitrine est à 10 et celui du milieu du dos à 20, la perle
     se place à 0,7×10 + 0,3×20 = 13.

   Donc quand un contrôleur bouge, son repère bouge, et la perle suit
   exactement de la part de ce contrôleur, comme dans Maya.
3. **Une courbe passe par ces perles** (le nœud « Spline From Points »
   d'Unreal). Les os de la colonne sont posés le long de la courbe (« Fit
   Chain on Spline Curve »). Ils gardent leur longueur, puisque Murakami ne
   s'étire pas.
4. **La règle en plus s'applique ensuite :** Spine4 tourne comme la poitrine,
   comme dans Maya.
5. **La correction de repos** (expliquée juste en dessous).

### Ce qui n'allait pas et comment on l'a corrigé

**1. La colonne se pliait autrement que dans Maya.**
- *Pourquoi :* chaque perle n'avait des repères que pour ses deux
  contrôleurs les plus forts et ignorait les autres. Or certaines perles sont
  tirées par trois contrôleurs.
- *Correction :* chaque perle a maintenant un repère pour **chaque**
  contrôleur qui tire dessus, avec les poids exacts de Maya.

**2. La colonne s'étirait alors que celle de Maya ne s'étire pas.**
- *Pourquoi :* l'étirement était activé par défaut.
- *Correction :* il est désactivé, sauf si l'exporteur détecte un étirement
  dans Maya.

**3. Une minuscule erreur de la colonne ruinait les genoux** (expliqué en
détail dans la partie E).
- *Pourquoi :* l'outil d'Unreal qui « pose les os sur la courbe » est une
  approximation. Même au repos, il plaçait les os de la colonne à environ
  **0,04 cm** (0,4 mm) de leur place. Tout ce qui est accroché à la colonne
  (hanches, épaules) héritait de cette erreur.
- *Correction (correction de repos) :* juste après la construction, le
  builder fait tourner le rig une fois au repos et mesure de combien chaque
  os de la colonne s'est écarté de sa place. Il écrit ensuite dans le rig un
  petit décalage correcteur pour chaque os et recompile. À partir de là, au
  repos, la colonne est exacte. Le journal affiche « largest rest offset
  0.0379 cm ».

**4. chest_ctrl était à 0,59 cm de sa place dans Maya** (spine_ctrl_01 :
0,065 cm).
- *Pourquoi :* Unreal plaçait chaque contrôleur de la colonne sur
  l'**articulation d'aide cachée** au lieu du contrôleur d'animateur. Ils
  sont proches mais pas au même endroit, donc le contrôleur tournait autour
  du mauvais point.
- *Correction :* l'exporteur envoie maintenant le pivot propre du contrôleur
  d'animateur (et dessine sa forme autour de ce pivot), et Unreal place le
  contrôleur là. La courbe ne change pas, car les perles sont placées
  séparément.

**Ce qui reste :** jusqu'à 0,056 cm (un demi-millimètre) sur Spine3 quand on
tourne les contrôleurs de la colonne. Ça vient de l'outil de courbe d'Unreal,
légèrement différent de celui de Maya. C'est dans l'objectif.

---

## Partie E : les bras et les jambes (membres IK/FK)

### Comment Maya fait
Chaque bras ou jambe a **3 vraies articulations** : épaule, coude, poignet
(ou hanche, genou, cheville). Derrière elles se cachent **deux copies
invisibles** du membre :
- une **copie IK**, bougée par le contrôleur de la main ou du pied et le
  pole vector ;
- une **copie FK**, bougée par les contrôleurs FK.

Les vraies articulations copient un mélange des deux, réglé par
l'interrupteur : 0 = tout IK, 1 = tout FK. Les copies sont accrochées à
Spine1 (jambes) et à Spine4 (bras).

Ce qu'on a **mesuré** dans Maya :
- les poignets et les chevilles ne tournent **pas** avec le contrôleur IK (ils
  gardent leur propre rotation) ;
- le genou reste toujours exactement dans le plan formé par la hanche, le
  pied et le pole vector ;
- les bras et les jambes de Murakami sont **parfaitement droits** au repos.
  C'était la source du problème le plus difficile.

### Comment Unreal les reconstruit
- **Les contrôleurs :** les contrôleurs FK, le contrôleur IK de la main ou du
  pied, le pole vector, et l'interrupteur (avec son curseur `IK_FK`).
- **L'IK :** le nœud IK à deux os d'Unreal (il calcule comment le coude ou le
  genou doit se plier pour atteindre la cible).
  - **L'interrupteur règle la force de l'IK :** en FK l'IK est complètement
    éteinte, en IK elle est complètement allumée.
  - **Les longueurs des os sont fixées** à leurs longueurs au repos.

### Ce qui n'allait pas et comment on l'a corrigé

**1. « Quand je tourne les contrôleurs FK, les 3 os bougent comme s'il y
avait une IK attachée. »**
- *Pourquoi :* l'IK restait en partie active en mode FK, et l'os du bout
  (poignet ou cheville) était mal géré.
- *Correction :* l'interrupteur règle maintenant directement la force de
  l'IK, donc le FK éteint vraiment l'IK. L'os du bout est géré à part (les
  deux points suivants).

**2. La rotation du poignet n'était pas appliquée du tout.**
- *Pourquoi :* on branchait la rotation sur une entrée nommée « Rotation »,
  mais sur ce nœud Unreal la vraie entrée s'appelle « **Value** ».
- *Correction :* branchée sur « Value ».

**3. Les poignets tournaient avec le contrôleur IK.**
- *Pourquoi :* j'avais supposé que ceux de Maya le font. Mesure faite, non.
- *Correction :* en IK, le poignet ou la cheville garde sa rotation de repos
  (sauf si le plan dit que le poignet de ce rig suit vraiment le
  contrôleur).

**4. Les hanches et les épaules ne suivaient pas la colonne.**
- *Pourquoi :* dans Maya, les jambes sont accrochées à l'articulation de la
  colonne. Dans Unreal, elles étaient accrochées au contrôleur du bassin,
  donc quand on bougeait la colonne, les jambes restaient derrière.
- *Correction (« root rebase ») :* Unreal prend la pose de la jambe, la
  mesure par rapport au contrôleur du bassin, puis la réapplique par rapport
  à un point d'aide qui suit l'articulation de la colonne. Les jambes suivent
  maintenant la colonne comme dans Maya. C'est fait pour chaque articulation
  du membre.

**5. Le genou était à 3,16 cm de sa place quand on tournait la poitrine.**
C'était le plus difficile.

- **Une corde tendue.** Imagine la jambe comme une corde tendue entre la
  hanche et la cheville. Si la hanche se rapproche un tout petit peu de la
  cheville, la corde prend un peu de mou et le milieu (le genou) ressort sur
  le côté. Comme la jambe est parfaitement droite, un tout petit peu de mou
  fait beaucoup ressortir le genou :
  - la jambe de Murakami fait environ 6 m ;
  - tourner la poitrine rapproche la hanche de la cheville de **0,04 cm** ;
  - dans Maya, le genou ressort alors de **3 cm**.
- **Deux raisons pour lesquelles le genou d'Unreal ne ressortait pas :**
  - l'IK d'Unreal mesurait la longueur de la jambe à partir de la pose
    actuelle. Si cette pose était décalée d'un cheveu, la jambe devenait
    « plus longue » et restait droite ;
  - l'erreur de repos de 0,04 cm de la colonne (partie D, point 3) avait
    remonté la hanche dans Unreal, donc la jambe avait déjà exactement ce mou
    *au repos*. La rotation de la poitrine ne faisait qu'utiliser ce mou, et
    le genou ne ressortait jamais.
- **Corrections :** longueurs des os fixées sur l'IK, plus la correction de
  repos de la colonne. Le genou est passé de **3,16 cm à 0,15 cm**.

### Pourquoi on voit encore 0,15 cm (genou) et 0,39 cm (coude), et pourquoi ce n'est pas grave

Même idée de la corde. Quand un membre est presque parfaitement droit, la
position du genou ou du coude dépend **énormément** de la distance exacte
hanche–cheville (ou épaule–poignet). Pour le bras droit de 7 m de Murakami,
une différence de 0,0005 cm (cinq millièmes de millimètre) déplace le coude
d'environ 0,4 cm.

Le fichier de test enregistre les positions arrondies à 0,0001 cm, donc même
les données de Maya ne peuvent pas situer le coude plus précisément que ça.
Mains, pieds, épaules et hanches correspondent tous. Ce n'est donc pas une
différence de rig, et le testeur sait en tenir compte (partie H4).

---

## Partie F : « qui suit quoi » (espaces parents et contraintes)

### F1. Suivre une articulation (espaces de suivi)

Parfois, le parent Maya d'un contrôleur n'est pas ce qui le fait vraiment
bouger, parce qu'une contrainte bouge son groupe à la place. L'exporteur
détermine alors **quelle articulation cette contrainte suit vraiment**.
Unreal crée un point invisible qui suit cette articulation, et place le
contrôleur dessous.

**Ce qui n'allait pas :** le contrôleur de l'orteil suivait le **genou**.
- *Pourquoi, raison 1 :* le curseur de l'interrupteur est aussi branché sur la
  contrainte (pour régler ses poids), et l'exporteur prenait ce fil pour
  « une chose que la contrainte suit ».
- *Pourquoi, raison 2 :* les copies cachées IK/FK de la jambe sont exactement
  superposées aux vraies articulations, donc l'exporteur choisissait parfois
  une copie cachée.

*Correction :* l'exporteur ne compte plus que les vraies cibles « à suivre »
(pas les fils de poids) et préfère les vraies articulations aux copies
cachées.

*Découverte au passage :* une ancienne copie de cette même fonction, plus bas
dans le fichier, remplaçait en douce la version corrigée. On a supprimé
l'ancienne copie, et vérifié que le plan exporté pour Murakami est identique
avec ou sans elle.

### F2. Suivre deux choses à la fois (le contrôleur FK du pied)

`L_FootFKctrl` (le contrôleur de l'orteil) suit **à la fois** le contrôleur IK
du pied et le dernier contrôleur FK de la jambe, mélangés par
l'interrupteur : en IK il suit le pied IK, en FK il suit la jambe FK.

- **Ce qu'on envoie :** les deux choses qu'il suit, quel curseur règle le
  mélange (et s'il est inversé), et où se trouve le contrôleur quand il ne
  suit *que* l'une des deux (mesuré en basculant l'interrupteur dans Maya,
  puis en le remettant).
- **Comment Unreal le reconstruit :** un point invisible mélangé entre les
  deux, avec le mélange lu en direct sur le curseur de l'interrupteur.

**Ce qui n'allait pas :** dans les poses FK, l'orteil était décalé de
1,0114 cm.
- *Pourquoi :* dans Maya, « suivre A ou B » retient **une distance séparée
  pour A et pour B**, fixée quand le rigger l'a créée. Sur Murakami, les deux
  ne sont pas d'accord : basculer l'interrupteur de IK à FK au repos fait
  **descendre de 1 cm l'orteil de Maya lui-même** (vérifié dans Maya). La
  version d'Unreal ne retient **qu'une seule** distance, mesurée au repos,
  donc elle ne pouvait pas reproduire cette descente.
- *Correction :* Unreal utilise maintenant deux points invisibles, un par
  chose suivie, chacun placé exactement là où Maya met le contrôleur quand il
  ne suit que celle-là. Il mélange entre les deux, donc il reproduit
  exactement la descente de Maya.

Pense à deux règles graduées. Maya mesure avec une règle différente pour l'IK
et pour le FK, alors qu'Unreal n'en avait qu'une. Maintenant Unreal a les
deux règles.

### F3. Les contraintes sur les articulations

Les règles Maya du type « cette articulation tourne comme ce contrôleur »
deviennent des nœuds de règle dans Unreal. Un détail compte : Maya retient la
distance de départ **du point de vue du parent de l'articulation**. Unreal a
deux versions de ces nœuds. On utilise celle qui fait pareil (« Local Space
Offset »). L'autre version la retient dans les coordonnées du monde, et
l'articulation dérive petit à petit dès que son parent tourne.

---

## Partie G : le cou, l'orteil, les yeux et les pétales (parties FK)

### Comment Maya fait
Un contrôleur par articulation, chacun bougeant son articulation :
- `neck_ctrl_01` à `05` et `head_ctrl` ;
- les contrôleurs des pétales `pedal_ctrl_01` à `12` ;
- les contrôleurs des yeux ;
- `L_FootFKctrl` pour l'orteil.

### Comment Unreal les reconstruit
Pour chaque articulation : un contrôleur placé sur le pivot Maya (avec
l'astuce du crochet si besoin), sous son parent Maya ou son point de suivi
(partie F). À chaque image, l'articulation copie le contrôleur (ou son
crochet).

### Ce qui n'allait pas et comment on l'a corrigé

**1. Les pétales ne suivaient pas la tête, et s'envolaient très loin quand la
tête tournait.**
- *Pourquoi :* le point de suivi des pétales suivait une articulation que les
  pétales bougent eux-mêmes. C'est une boucle : contrôleur → articulation →
  point de suivi → contrôleur, qui s'emballe dès que quelque chose bouge.
  Certains points de suivi suivaient aussi des articulations que personne ne
  bouge.
- *Correction :* le builder détecte ces boucles et suit l'articulation parente
  à la place. Il prévient aussi quand un point de suivi surveille une
  articulation que rien ne bouge.

**2. Les pétales tournaient autour du milieu de leur forme, pas de leur pivot
personnalisé.**
- *Pourquoi :* on utilisait le milieu de la forme comme pivot.
- *Correction :* on utilise maintenant le vrai pivot. Le milieu sert seulement
  quand le pivot a été laissé au centre du monde.

**3. Les contrôleurs du cou étaient décalés de 0,11 à 0,13 cm** (ceux des bras
d'environ 0,005 cm).
- *Pourquoi :* tout contrôleur à moins de 0,5 cm de son articulation était
  « collé » sur l'articulation, considéré comme « assez proche ». Mais ça
  déplace son pivot.
- *Correction :* la limite de collage est maintenant de 0,001 cm (en gros,
  seulement le bruit d'arrondi). Chaque vrai pivot est conservé, grâce à
  l'astuce du crochet.

**4. L'orteil était à 1 cm de sa place au repos :** le problème pose de
liaison / pose de repos (partie C4).

**5. L'orteil était décalé de 1 cm dans les poses FK de la jambe gauche :**
le problème des deux règles graduées (partie F2).

---

## Partie H : le testeur (test de poses)

### H1. Comment il fonctionne

- **Dans Maya** (`export_test_poses.py`, lancé pendant l'export) :
  - **repos :** personne ne touche à rien ;
  - **sondes :** chaque contrôleur bougé dans un seul sens à la fois
    (rotation de 20° ou déplacement de 5 cm), avec le bras ou la jambe dans
    le bon mode (IK ou FK) pour ce contrôleur ;
  - **12 poses aléatoires :** plusieurs contrôleurs bougés en même temps.

  Pour chaque pose, il enregistre où se trouve chaque articulation et comment
  elle est tournée.
- **Dans Unreal** (`pose_harness.py`), pour chaque pose :
  1. remettre le rig au repos ;
  2. bouger chaque contrôleur de la même façon que dans Maya, en tournant
     autour du même pivot ;
  3. régler les curseurs des interrupteurs ;
  4. laisser le rig calculer, replacer les contrôleurs, et calculer deux
     fois de plus ;
  5. lire où chaque os a fini.
- **La comparaison :** de combien chaque os a bougé depuis le repos dans
  Unreal, contre de combien il a bougé dans Maya. Comparer le *mouvement* (et
  pas la position brute) évite qu'un os légèrement décalé au repos compte
  comme faux à chaque pose.
- **Calibration** d'abord : au repos, les os et les contrôleurs sont-ils là où
  Maya le dit ? Si la plupart sont décalés, c'est la traduction elle-même qui
  est cassée, et le rapport dit de ne pas se fier au reste.
- **Le rapport** donne une note par partie (T0 / T1 / au-dessus de T1), les
  pires contrôleurs, les pires poses, et « mieux / moins bien que la dernière
  fois ». Il y a aussi une page HTML.

### H2. Erreurs dans le testeur lui-même (aussi corrigées)

| Ce qui n'allait pas | Ce qu'on a changé |
|---|---|
| Les contrôleurs au pivot déplacé étaient rejoués en tournant autour du mauvais point | On rejoue le mouvement complet, pivot compris |
| La photo de repos de Maya était prise avant que le rig se soit stabilisé | On la reprend après stabilisation |
| Un os légèrement décalé au repos comptait comme faux à chaque pose | On compare le mouvement, pas la position |
| La calibration échouait à cause d'un ou deux os mal placés | Elle n'échoue que si *la plupart* des os sont décalés ; les quelques-uns sont listés comme « décalés au repos » |
| Les copies cachées IK/FK des jambes étaient notées alors qu'Unreal ne les utilise pas | On ne note que les articulations qu'Unreal construit vraiment ; les autres sont listées |
| Certaines sondes utilisaient le mauvais mode IK/FK | Le mode de chaque contrôleur est retrouvé correctement |
| L'orteil affichait 17° / 9 cm sur une pose aléatoire | Son contrôleur était placé avant que la chose qu'il suit ait bougé ; maintenant les contrôleurs sont replacés après le premier calcul |
| Pas de fichier de poses après l'export | Maya gardait en mémoire l'ancienne version de notre code. Le bouton de l'étagère (shelf) recharge maintenant tout, y compris les fichiers ajoutés après le démarrage de Maya. |

### H3. Les « 0,14° » des pétales : une erreur de mesure, pas un problème de rig

Tous les pétales affichaient la même petite erreur de 0,13–0,15°, alors que
les pétales de Maya ne bougeaient pas du tout.

**Pourquoi :** les rotations sont stockées dans le fichier de test sous forme
de quatre nombres arrondis. La formule qu'on utilisait pour calculer
« l'angle entre deux rotations » est extrêmement sensible près de zéro. Elle
transformait un arrondi sans importance (0,0000003) en un faux 0,1°. La
preuve : la pose de repos n'était **pas d'accord avec elle-même**, de
0,1355°.

**Correction :** une autre formule, qui n'est pas sensible près de zéro. Les
pétales sont maintenant notés T0 (parfait).

### H4. Le testeur et les membres droits

À cause de l'effet de la corde (partie E), le testeur signalerait toujours les
genoux et les coudes des membres droits, même quand le rig est juste. Donc,
pour chaque bras et chaque jambe, le testeur calcule maintenant quelle part de
l'erreur du genou ou du coude est **expliquée** par :
1. la hanche et la cheville (ou l'épaule et le poignet) elles-mêmes
   légèrement décalées dans cette pose ;
2. la distance exacte hanche–cheville dans Unreal comparée à Maya ;
3. l'arrondi du fichier de test.

Seule la part **non expliquée** compte dans la note. Sur un membre plié,
presque rien n'est « expliqué » : dans notre test, une fausse erreur de
0,3 cm au coude d'un bras plié comptait encore 0,299. Les vrais problèmes
restent donc visibles. Les chiffres bruts restent affichés dans une section
« Near-straight limbs » (membres presque droits).

Sur Murakami : coudes 0,39 cm et genoux 0,15–0,19 cm en brut, **entièrement
expliqués**.

---

## Partie I : d'où on est parti, où on en est

| | Début de cette série | Maintenant |
|---|---|---|
| Parties identiques à Maya (à 1 mm près) | 16 sur 21 | **21 sur 21** |
| Os décalés au repos | orteil à 1 cm ; la plupart des os à 0,04 cm | aucun (la plupart à moins de 0,0003 cm) |
| Genou quand on tourne la poitrine | 3,16 cm | 0,15 cm, entièrement expliqué |
| Orteil | 1 cm au repos ; 17° sur une pose | parfait (T0) |
| Pétales | 0,14° | parfait (T0) |
| Pire contrôleur par rapport à son pivot Maya | 1 cm (orteil), 0,59 cm (poitrine) | 0,013 cm |

## Partie J : leçons pour le prochain personnage

1. **Mesurer dans Maya, ne pas deviner.** Plusieurs corrections sont venues
   uniquement de tests sur la vraie scène Maya (une copie, jamais ton
   fichier) : les poignets qui ne suivent pas l'IK, l'orteil qui descend au
   passage IK→FK, la pose de liaison de l'orteil.
2. **La pose de liaison et la pose de repos peuvent différer.** L'outil gère
   ça automatiquement maintenant.
3. **Les bras et les jambes droits amplifient les petites erreurs.** Une
   erreur de 0,4 mm dans la colonne est devenue une erreur de 3 cm au genou.
4. **Le « suivre A ou B » de Maya garde une distance séparée pour chacun ;**
   celui d'Unreal n'en garde qu'une. L'outil copie maintenant celui de Maya.
5. **Maya répond en cm ou en mètres selon la façon dont on lui demande.**
6. **Vérifier aussi l'outil de mesure :** une mauvaise formule a inventé les
   0,14° des pétales.
7. **Le Python d'Unreal a ses bizarreries :** des fonctions qui manquent, et
   des entrées nommées autrement que ce que le nœud affiche.

## Partie K : lire le graphe de nœuds dans Unreal

Quand tu ouvres le Control Rig, le graphe est maintenant rangé
automatiquement :
- **Chaque partie du rig est dans sa propre boîte** (un *comment*), avec son
  nom et son type en titre, par exemple « Spine (SplineIK) » ou
  « L_LegLeaf (IKFKSwitch) ». La couleur dépend du type :
  - bleu = colonne (spline) ;
  - orange = bras et jambes (IK/FK) ;
  - vert = parties FK (cou, orteil, yeux, pétales) ;
  - gris = le départ (Forwards Solve et l'ordre de calcul).
- **Dans une boîte, le calcul se lit de gauche à droite.** Un nœud est
  toujours à droite des nœuds qui l'alimentent, et un nœud qui ne fait que
  « lire » quelque chose (par exemple un *Get Transform*) est placé juste à
  gauche du nœud qu'il alimente.
- **Rien ne se chevauche :** ni les nœuds dans une boîte, ni les boîtes entre
  elles. Les boîtes sont empilées de haut en bas dans l'ordre de
  construction, puis en nouvelles colonnes vers la droite.
- **À chaque reconstruction,** les anciennes boîtes sont supprimées et le
  rangement est refait. Le journal affiche « Graph laid out: N node(s) in M
  named box(es) ».

## Partie L : ce qui reste à faire

- **Les curseurs d'ouverture/fermeture des pétales** (`Petal_Translate` /
  `Petal_Rotation`). Dans Maya, ces curseurs pilotent les pétales à travers un
  réseau de nœuds de calcul, que notre outil ne traduit pas encore.
