import psycopg2
from datetime import datetime
import streamlit as st

st.title("Gestion de stock")

# --- Mot de passe ---
try:
    MOT_DE_PASSE = st.secrets["mot_de_passe"]
except Exception:
    st.error("Mot de passe non configuré")
    st.stop()

if not st.session_state.get("connecte"):
    saisie = st.text_input("Mot de passe", type="password")
    if st.button("Se connecter"):
        if saisie == MOT_DE_PASSE:
            st.session_state["connecte"] = True
            st.rerun()
        else:
            st.error("Mot de passe incorrect")
    st.stop()


def connecter():
    return psycopg2.connect(st.secrets["database_url"])


if st.session_state.get("message"):
    st.success(st.session_state["message"])
    st.session_state["message"] = ""

connexion = connecter()
curseur = connexion.cursor()
curseur.execute("SELECT id, categorie, nom_modele, prix_vente, prix_achat, quantite_stock FROM produits ORDER BY categorie, prix_vente")
produits = curseur.fetchall()

aujourdhui = datetime.now().strftime("%Y-%m-%d")
curseur.execute("SELECT COALESCE(SUM((prix_vente_reel - COALESCE(prix_achat, 0)) * quantite), 0) FROM ventes")
benefice_total = curseur.fetchone()[0]
curseur.execute(
    "SELECT COALESCE(SUM((prix_vente_reel - COALESCE(prix_achat, 0)) * quantite), 0) FROM ventes WHERE date_vente LIKE %s",
    (aujourdhui + "%",)
)
benefice_jour = curseur.fetchone()[0]

curseur.execute("""
SELECT v.date_vente, p.nom_modele, v.quantite, v.prix_vente_reel,
       (v.prix_vente_reel - COALESCE(v.prix_achat, 0)) * v.quantite
FROM ventes v
JOIN produits p ON p.id = v.produit_id
WHERE v.date_vente LIKE %s
ORDER BY v.id DESC
""", (aujourdhui + "%",))
ventes_du_jour = curseur.fetchall()
curseur.close()
connexion.close()

# --- Bénéfices ---
col1, col2 = st.columns(2)
col1.metric("Bénéfice aujourd'hui", f"{benefice_jour} F")
col2.metric("Bénéfice total", f"{benefice_total} F")

# --- Ventes d'aujourd'hui ---
st.subheader("Ventes d'aujourd'hui")

if len(ventes_du_jour) == 0:
    st.info("Aucune vente aujourd'hui")

for date_vente, nom_vendu, qte, prix_v, benef in ventes_du_jour:
    st.write(f"{date_vente[11:]} - {qte} x **{nom_vendu}** à {prix_v} F - bénéfice : {benef} F")

# --- Liste du stock ---
st.subheader("Stock")

if len(produits) == 0:
    st.info("Aucun produit pour l'instant")

categorie_actuelle = None
for id_produit, categorie, nom_produit, prix, prix_achat_produit, stock in produits:
    if categorie != categorie_actuelle:
        st.markdown(f"### {categorie}")
        categorie_actuelle = categorie

    if stock == 0:
        st.write(f"**{nom_produit}** - {prix} F - 🔴 Fini")
    else:
        st.write(f"**{nom_produit}** - {prix} F - {stock} en stock")

# --- Vendre un produit ---
st.subheader("Vendre un produit")

if len(produits) > 0:
    noms = [f"{p[1]} - {p[2]} ({p[3]} F)" for p in produits]
    choix = st.selectbox("Produit vendu", noms)
    id_produit, categorie, nom_produit, prix, prix_achat_produit, stock = produits[noms.index(choix)]

    quantite_vendue = st.number_input("Quantité vendue", min_value=1, step=1)
    prix_reel = st.number_input("Prix de vente réel (F par pièce)", min_value=0, step=500, value=int(prix))

    if st.button("Valider la vente"):
        if quantite_vendue > stock:
            st.error(f"Impossible : il ne reste que {stock} en stock")
        else:
            achat = prix_achat_produit or 0
            benefice = (prix_reel - achat) * quantite_vendue

            connexion = connecter()
            curseur = connexion.cursor()
            curseur.execute(
                "UPDATE produits SET quantite_stock = quantite_stock - %s WHERE id = %s",
                (quantite_vendue, id_produit)
            )
            curseur.execute(
                "INSERT INTO ventes (produit_id, quantite, prix_vente_reel, prix_achat, date_vente) VALUES (%s, %s, %s, %s, %s)",
                (id_produit, quantite_vendue, prix_reel, achat, datetime.now().strftime("%Y-%m-%d %H:%M"))
            )
            connexion.commit()
            curseur.close()
            connexion.close()
            st.session_state["message"] = f"Vente enregistrée : {quantite_vendue} x {nom_produit} - bénéfice : {benefice} F"
            st.rerun()

# --- Ajouter du stock (nouvelle livraison) ---
st.subheader("Ajouter du stock (nouvelle livraison)")

if len(produits) > 0:
    choix_recu = st.selectbox("Produit reçu", noms)
    id_recu, categorie_recu, nom_recu, prix_recu, achat_recu, stock_recu = produits[noms.index(choix_recu)]

    quantite_recue = st.number_input("Quantité reçue", min_value=1, step=1)
    nouveau_prix_achat = st.number_input("Prix d'achat (F par pièce)", min_value=0, step=500, value=int(achat_recu or 0))

    if st.button("Ajouter au stock"):
        connexion = connecter()
        curseur = connexion.cursor()
        curseur.execute(
            "UPDATE produits SET quantite_stock = quantite_stock + %s, prix_achat = %s WHERE id = %s",
            (quantite_recue, nouveau_prix_achat, id_recu)
        )
        connexion.commit()
        curseur.close()
        connexion.close()
        st.session_state["message"] = f"Stock ajouté : {quantite_recue} x {nom_recu}"
        st.rerun()

# --- Ajouter un nouveau produit ---
st.subheader("Ajouter un nouveau produit")

categories = sorted(set(p[1] for p in produits))
choix_categorie = st.selectbox("Catégorie", categories + ["➕ Nouvelle catégorie"])
if choix_categorie == "➕ Nouvelle catégorie":
    categorie_saisie = st.text_input("Nom de la nouvelle catégorie")
else:
    categorie_saisie = choix_categorie

nom = st.text_input("Nom du modèle")
prix_vente = st.number_input("Prix de vente conseillé (F)", min_value=0, step=500)
prix_achat = st.number_input("Prix d'achat (F)", min_value=0, step=500)
quantite = st.number_input("Quantité", min_value=0, step=1)

if st.button("Ajouter"):
    if nom.strip() == "" or categorie_saisie.strip() == "":
        st.error("Écris la catégorie et le nom du modèle")
    else:
        connexion = connecter()
        curseur = connexion.cursor()
        curseur.execute(
            "INSERT INTO produits (categorie, nom_modele, prix_vente, prix_achat, quantite_stock) VALUES (%s, %s, %s, %s, %s)",
            (categorie_saisie.strip(), nom.strip(), prix_vente, prix_achat, quantite)
        )
        connexion.commit()
        curseur.close()
        connexion.close()
        st.session_state["message"] = "Produit ajouté"
        st.rerun()

# --- Corriger un produit ---
st.subheader("Corriger un produit")

if len(produits) > 0:
    choix_corr = st.selectbox("Produit à corriger", noms)
    id_c, cat_c, nom_c, prix_c, achat_c, stock_c = produits[noms.index(choix_corr)]

    corr_nom = st.text_input("Nom du produit (modifie-le si besoin)", value=nom_c, key=f"corr_nom_{id_c}")
    corr_prix_vente = st.number_input("Nouveau prix de vente (F)", min_value=0, step=500, value=int(prix_c), key=f"corr_pv_{id_c}")
    corr_prix_achat = st.number_input("Nouveau prix d'achat (F)", min_value=0, step=500, value=int(achat_c or 0), key=f"corr_pa_{id_c}")
    corr_stock = st.number_input("Nouvelle quantité en stock", min_value=0, step=1, value=int(stock_c), key=f"corr_st_{id_c}")

    if st.button("Enregistrer les corrections"):
        if corr_nom.strip() == "":
            st.error("Le nom ne peut pas être vide")
        else:
            connexion = connecter()
            curseur = connexion.cursor()
            curseur.execute(
                "UPDATE produits SET nom_modele = %s, prix_vente = %s, prix_achat = %s, quantite_stock = %s WHERE id = %s",
                (corr_nom.strip(), corr_prix_vente, corr_prix_achat, corr_stock, id_c)
            )
            connexion.commit()
            curseur.close()
            connexion.close()
            st.session_state["message"] = f"Produit corrigé : {corr_nom.strip()}"
            st.rerun()

    st.markdown("**Supprimer ce produit**")
    confirmer = st.checkbox("Je confirme vouloir supprimer ce produit", key=f"conf_{id_c}")
    if st.button("Supprimer"):
        if not confirmer:
            st.error("Coche d'abord la case de confirmation")
        else:
            connexion = connecter()
            curseur = connexion.cursor()
            curseur.execute("SELECT COUNT(*) FROM ventes WHERE produit_id = %s", (id_c,))
            nb_ventes = curseur.fetchone()[0]
            if nb_ventes > 0:
                curseur.close()
                connexion.close()
                st.error("Ce produit a déjà des ventes, il ne peut pas être supprimé. Mets son stock à 0 à la place.")
            else:
                curseur.execute("DELETE FROM produits WHERE id = %s", (id_c,))
                connexion.commit()
                curseur.close()
                connexion.close()
                st.session_state["message"] = f"Produit supprimé : {nom_c}"
                st.rerun()