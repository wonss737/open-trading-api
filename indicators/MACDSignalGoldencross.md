/*
A=MACD(가격,단기,장기,이평방법);
B=MA(A,시그널기간,이평방법);
Crossup(A,B);
*/

Params :
	ShortPeriod(12),			//단기
	LongPeriod(26),				//장기
	SignalPeriod(9),			//시그널기간
	_PRICE_(C),					//가격
	_MaType_(1) ;				//이평방법

Vars :
	v1(0),
	v2(0);

v1 = MACD(_PRICE_, ShortPeriod, LongPeriod, _MaType_) ;

if CB >= LongPeriod Then v2 = MA_EX(v1, SignalPeriod, _MaType_);

if Crossup( v1, v2) And CB >= LongPeriod Then
	Plot1(C, "MACD-SIG와골든크로스");
