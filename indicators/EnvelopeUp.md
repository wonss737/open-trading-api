/*
EnvelopeUp(Price,Period,Percent,이평방법)

MA(Price,Period,이평방법)
+
(MA(Price,Period,이평방법)*Percent/100)
*/

Params :
	_PRICE_(NumSimple),		//가격
	Period(NumSimple),		//기간
	Pcent(NumSimple),		//퍼센트
	_MaType_(NumSimple);	//이평방법

Vars :
	v1(0);

v1 = MA( _PRICE_, Period, _MaType_ );

EnvelopeUp = v1 + (v1 * Pcent /100 );