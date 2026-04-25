//BBandsUp(Price,Period,승수,이평방법)
//MA(Price,Period,이평방법)+승수*stdev(Price,Period)
Params :
	_PRICE_(NumSimple),		//가격
	Period(NumSimple),		//기간
	Multi(NumSimple),		//승수
	_MaType_(NumSimple);		//이평방법

Vars :
	v1(0),
	v2(0);

v1 = MA_EX(_PRICE_, Period, _MaType_) ;
v2 = Multi * StdDev( _PRICE_, Period, _MAType_ );

if CB > Period - 1 Then BBandsUp = v1 + v2 ;