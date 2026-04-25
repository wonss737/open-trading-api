// MaType_Extends : CB >= pPeriod 추가
// 현재 봉의 번호가 Period 보다 작은 경우도 계산 가능한 개선된 MA 함수
// 0:단순,  1:지수,  2:가중,  3:기하,  4:조화,  5:삼각이평
Params :
		pPriceVal( NumSeries ),
		pPeriod( NumSimple ),
		_MaType_( NumSimple );

Vars :
		Cnt( 0 ),
		vSumVal(0),
		vCSumVal(0),
		vResult(0),
		vConstVal(0.5),
		v0(0),
		v1(0),
		v2(0);

Array : Value[1](0);

vResult = 0;
v0 = 0;

//-------------------------------------------------------------------------------

if _MaType_ = 0 Then								// _MaType_ = 0 단순이평
Begin
	if CB >= pPeriod Then							// 작도시점 제어
	Begin
		For Cnt = 0 to pPeriod - 1 step 1
		Begin
			v0 = v0 + pPriceVal[Cnt] ;
		End;
		If pPeriod <> 0 Then
			vResult = v0 / pPeriod
		Else
			vResult = 0;
	End;
End
//-------------------------------------------------------------------------------

Else if _MaType_ = 1 Then							// 지수이평
Begin
	if IsErrorValue(pPriceVal) = 1 Then
	Begin
	if CB > 1 Then
		vResult = vResult[1]
	else
		vResult = 0;
	End
	Else
	Begin
		if CB > 1 Then
		Begin
			if Value[0] <> 0 Then					// 1봉전 값 검사
			Begin
				vResult = Value[0] + 2/(pPeriod + 1) * ( pPriceVal - Value[0] );
				Value[0] = vResult;
			End
			Else
			Begin
				Value[0] = pPriceVal;
				vResult = pPriceVal;
			End;
		End
		else
		Begin
			Value[0] = pPriceVal;
			vResult = pPriceVal;
		End;
	End;
End

//-------------------------------------------------------------------------------

Else if _MaType_ = 2 Then							// 가중이평
Begin
	if CB >= pPeriod Then							// 작도시점 제어
	Begin
		for Cnt = 0 to pPeriod - 1 step 1
		Begin
			v0 = v0 + (pPeriod - Cnt) * pPriceVal[Cnt];
		End;

		v1 = (pPeriod + 1) * pPeriod * vConstVal;


		if v1 <= 0 Then
			vResult = 0
		else
			vResult = v0 / v1;
	End;
End

//-------------------------------------------------------------------------------

Else if _MaType_ = 3 Then							// 기하이평
Begin
	v0 = 1 ;
	if CB >= pPeriod Then							// 작도시점 제어
	Begin
		For Cnt = 0 to pPeriod - 1 Step 1
		Begin
			v0 = v0 * pPriceVal[Cnt] ;
		End;

			vResult = (v0)^(1/Cnt);
	End;
End

//-------------------------------------------------------------------------------

Else if _MaType_ = 4 Then							// 조화이평
Begin
	if CB >= pPeriod Then							// 작도시점 제어
	Begin
		For Cnt = 0 to pPeriod - 1 Step 1
		Begin
			v0 = v0 + 1/pPriceVal[Cnt] ;
		End;
			v1 = v0 / pPeriod ;
			vResult = 1 / v1 ;
	End;
End

//-------------------------------------------------------------------------------
Else if _MaType_ = 5 Then							// 삼각이평
Begin
	v0 = 0;
	v1 = 0;
	v2 = 0;
	if CB >= pPeriod Then
	Begin							// 작도시점 제어
		If Fracportion(pPeriod/2) <> 0 Then
		Begin
			for cnt = 0 To pPeriod - 1
			Begin
				if cnt <= (pPeriod + 1)/2 - 1 Then v0 = v0 + 1
				Else v0 = v0 - 1;

				v1 = v1 + pPriceVal[cnt] * v0;
				v2 = v2 + v0;
			End;

			vResult = 1/v2 * v1;
		End
		Else
		Begin
			for cnt = 0 To pPeriod - 1
			Begin
				if cnt < ceiling((pPeriod + 1)/2) - 1 Then v0 = v0 + 1
				Else if cnt > Ceiling((pPeriod + 1)/2) - 1 Then v0 = v0 - 1;

				v1 = v1 + pPriceVal[cnt] * v0;
				v2 = v2 + v0;
			End;

			vResult = 1/v2 * v1;
		End;
	End;
End;

MA_EX = vResult;