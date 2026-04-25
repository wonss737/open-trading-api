/*
EnvelopeMid(가격,이평기간,이평방법)
EnvelopeUp(가격,이평기간,비율,이평방법)
EnvelopeDown(가격,이평기간,비율,이평방법)
*/
Params :
	Period(20),			//이평기간
	UpRatio(6),			//상한비율
	DownRatio(6),		//하한비율
	_PRICE_(C),			//가격
	_MaType_(0);		//이평방법

Vars:
	v1(0),
	v2(0),
	v3(0);

v1 = EnvelopeMid(_PRICE_, Period, _MaType_);
v2 = EnvelopeUp(_PRICE_, Period, UpRatio, _MaType_);
v3 = EnvelopeDown(_PRICE_, Period, DownRatio, _MaType_);

if _MaType_ = 1 Then
Begin
	If CB >= Period Then
	Begin
		Plot1(v2, "E_상한선");
		Plot2(v1, "E_중심선");
		Plot3(v3, "E_하한선");
	End;
End
Else
Begin
	Plot1(v2, "E_상한선");
	Plot2(v1, "E_중심선");
	Plot3(v3, "E_하한선");
End;