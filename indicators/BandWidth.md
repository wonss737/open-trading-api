/*
Up=BBandsUp(가격,적용기간,승수,이평방법);
Down=BBandsDown(가격,적용기간,승수,이평방법);
Mid=BBandsMid(가격,적용기간,이평방법);
(Up-Down)/Mid
*/

Params :
	Period(20),			//적용기간
	Mult(2),			// 승수
	_PRICE_(C),			// 가격
	_MaType_(0);		//이평방법, 0은 단순이동평균

Variables :
	UpLine(0),
	DownLine(0),
	MidLine(0),
	v0(0);

UpLine = BBandsUp(_PRICE_, Period, Mult, _MaType_);
DownLine = BBandsDown(_PRICE_, Period, Mult, _MaType_);
MidLine = BBandsMid(_PRICE_, Period, _MaType_);

if MidLine <> 0 Then
	v0 = (UpLine - DownLine) / MidLine
Else
	v0 = 0;

if CB > Period - 1 Then Plot1(v0, "Band Width");
