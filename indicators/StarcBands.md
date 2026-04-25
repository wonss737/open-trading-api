Params :
	StarcPeriod(15),
	MAPeriod(6),
	Constant(2),
	_PRICE_(C);

Vars:
	v1(0),
	v2(0),
	v3(0);

if CB >= MAPeriod - 1 Then
Begin
	v1 = StarcMiddle(_PRICE_,MAPeriod);						//MiddleBand
	V2 = StarcUpper(_PRICE_,StarcPeriod,MAPeriod,Constant); //UpperBand
	V3 = StarcLower(_PRICE_,StarcPeriod,MAPeriod,Constant);	//LowerBand

	if CB >= StarcPeriod Then
	Begin
		Plot1(V2, "Starc Upper");
	End;

	Plot2(V1, "Starc Center");

	if CB >= StarcPeriod Then
	Begin
		 Plot3(V3, "Starc Lower");
	End;
End;

/*
Params :
	StarcPeriod(15),
	MAPeriod(6),
	Constant(2),
	_PRICE_(C);

Vars:
	v1(0),
	v2(0),
	v3(0);

v1 = StarcMiddle(_PRICE_,MAPeriod);						//MiddleBand
V2 = StarcUpper(_PRICE_,StarcPeriod,MAPeriod,Constant);	//UpperBand
V3 = StarcLower(_PRICE_,StarcPeriod,MAPeriod,Constant);	//LowerBand

Plot1(V2, "Starc Upper");
Plot2(V1, "Starc Center");
Plot3(V3, "Starc Lower");
*/