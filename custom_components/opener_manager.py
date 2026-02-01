import logging
import random
from typing import List, Optional

logger = logging.getLogger("opener_manager")

# Static list of openers as requested by the user
STATIC_OPENERS = [
    "Hallo, ik ben AVA. Samen kunnen we onderzoeken wat er op dit moment in jou leeft volgens de methode van Juno Burger en 'The Invitation', waarbij we alles wat zich aandient simpelweg herkennen en erkennen zonder het te willen veranderen. In plaats van te focussen op het verhaal of een oplossing, nodigen we de directe fysieke ervaring en energie uit om er helemaal te mogen zijn, precies zoals het nu is. Door waar te nemen wat er gebeurt in je comfortzone, triggerzone of reactiezone, ontstaat er ruimte voor co-regulatie en innerlijke rust. Begrijp je hoe we op deze manier samen aan de slag kunnen gaan?",
    "Hallo, ik ben AVA. Fijn dat je er bent. Ik werk volgens de filosofie van Juno Burger en de methode van *The Invitation*, waarbij we samen ruimte maken voor alles wat er op dit moment in jou aanwezig is. In plaats van iets te willen veranderen of op te lossen, nodigen we elke sensatie, emotie of gedachte simpelweg uit om er helemaal te mogen zijn, precies zoals het is. Door te herkennen en te erkennen wat er nu leeft, ontstaat er vaak vanzelf een natuurlijke ontspanning of ruimte. Is deze manier van werken duidelijk voor je, of zal ik er nog iets meer over vertellen?",
    "Hallo, ik ben AVA. Ik ben hier om samen met jou te verkennen wat er op dit moment in je leeft, volgens de methode van Juno Burger en 'The Invitation'. In plaats van dingen op te lossen of te veranderen, nodigt deze weg je uit om simpelweg waar te nemen en te erkennen wat er nu is, zodat er ruimte ontstaat voor je directe ervaring. We werken met het herkennen van je comfortzone, de plek waar spanning voelbaar wordt (de triggerzone) en de momenten waarop je volledig wordt overgenomen door een reactie. Het doel is niet om ergens vanaf te komen, maar om aanwezig te zijn bij alles wat zich aandient, precies zoals het is. Begrijp je hoe we op deze manier samen kunnen werken, of wil je dat ik er nog wat dieper op inga?",
    "Hallo, ik ben AVA. Ik werk met je volgens de methode van Juno Burger, genaamd The Invitation, waarbij we ons richten op het simpelweg waarnemen en laten zijn van je huidige ervaring. Het doel is niet om iets te fixen of te veranderen, maar om met compassie ruimte te maken voor alles wat zich aandient: van fysieke sensaties tot emoties of gedachten. Door te herkennen en erkennen wat er is, zonder oordeel, ontstaat er ruimte voor co-regulatie en aanwezigheid. Begrijp je deze manier van werken, of zal ik er nog wat dieper op ingaan voor we beginnen? Wat merk je op dit moment op in jezelf?"
]

# Static list of reconnection openers for returning users
RECONNECTION_OPENERS = [
    "Welkom terug, wat fijn om je weer te zien! Waar wil je het vandaag over hebben?",
    "Fijn dat je er weer bent! Hoe is het met je? Waar zullen we vandaag samen naar kijken?",
    "Welkom terug bij AVA. Wat leeft er op dit moment in je? Is er iets specifieks waar je vandaag ruimte voor wilt maken?",
    "Wat goed om je weer te zien. Zullen we de draad weer oppakken? Wat dient zich op dit moment aan in je ervaring?",
    "Welkom terug. Ik ben er weer om samen met jou met compassie waar te nemen wat er nu in je leeft. Waar wil je beginnen?"
]

class OpenerManager:
    def __init__(self, llm_adapter=None):
        # We keep the llm_adapter parameter for compatibility, but we don't use it anymore
        pass

    async def get_opener(self) -> str:
        """
        Return a random opener from the static list.
        """
        if not STATIC_OPENERS:
            return "Hallo, ik ben AVA. Samen kunnen we onderzoeken wat er op dit moment in jou leeft volgens de methode van Juno Burger en 'The Invitation'..."
        opener = random.choice(STATIC_OPENERS)
        logger.info(f"Selected static opener: {opener[:50]}...")
        return opener

    async def get_reconnection_opener(self) -> str:
        """
        Return a random reconnection opener for returning users.
        """
        if not RECONNECTION_OPENERS:
            return "Welkom terug, wat fijn om je weer te zien! Waar wil je het vandaag over hebben?"
        opener = random.choice(RECONNECTION_OPENERS)
        logger.info(f"Selected static reconnection opener: {opener[:50]}...")
        return opener

# Global instance
_opener_manager = None

def get_opener_manager(llm_adapter=None):
    global _opener_manager
    if _opener_manager is None:
        _opener_manager = OpenerManager(llm_adapter)
    return _opener_manager
