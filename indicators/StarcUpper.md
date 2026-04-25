Params :
 _PRICE_(NumSimple),
 StarcPeriod(NumSimple),
 MAPeriod(NumSimple),
 Constant(NumSimple);

Vars:
 v0(0);

IF CB > 1 Then
Begin
	v0 = Avg(_PRICE_, MAPeriod) + ATR(_PRice_,StarcPeriod) * Constant;
	StarcUpper = v0;
End;