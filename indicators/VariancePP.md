// StdDev.P
Params :
	Price( NumSeries ),
	Period( NumSimple ),
	_MAType_( NumSimple );

Vars :
	v1(0),
	v2(0),
	v3(0),
	ii(0),
	vtemp(0);

if _MaType_ = 1 Then
Begin
	if CB > Period - 1 Then
	Begin
		v3 = MA(Price, Period, _MaType_);

		For ii = 0 To Period - 1
		Begin
			v2 = Price[ii] - v3;
			vtemp = vtemp + (v2 * v2);
		End;

		vtemp = vtemp / Period; // StdDev.P 계산
		v1 = vtemp;

		//vtemp 초기화
		vtemp = 0;
	End;
End
Else
Begin
	if CB > Period - 1 Then
	Begin
		v3 = MA_EX(Price, Period, _MaType_);

		For ii = 0 To Period - 1
		Begin
			v2 = Price[ii] - v3;
			vtemp = vtemp + (v2 * v2);
		End;

		vtemp = vtemp / Period; // StdDev.P 계산
		v1 = vtemp;

		//vtemp 초기화
		vtemp = 0;
	End;
End;

VariancePP = V1;